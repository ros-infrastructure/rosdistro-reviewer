# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import copy
from functools import lru_cache
import itertools
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from colcon_core.environment_variable import EnvironmentVariable
from colcon_core.generic_decorator import GenericDecorator
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from git import Repo
from rosdistro_reviewer.element_analyzer import ElementAnalyzerExtensionPoint
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation
from rosdistro_reviewer.yaml_changes import get_changed_yaml
from rosdistro_reviewer.yaml_changes import prune_changed_yaml
import yaml

"""Environment variable for the GitHub Actions event file path"""
GITHUB_EVENT_PATH_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'GITHUB_EVENT_PATH',
    'Path to the GitHub Actions event file containing event payload JSON')

logger = colcon_logger.getChild(__name__)

MINIMUM_BLOOM_VERSIONS = {
    'humble': (0, 12, 0),
    'jazzy': (0, 12, 0),
    'kilted': (0, 12, 0),
    'lyrical': (0, 14, 3),
    'rolling': (0, 14, 3),
}


def _parse_version(version_str: str) -> Tuple[int, ...]:
    return tuple(
        int(x) for x in itertools.takewhile(
            str.isdigit, version_str.split('.'))
    )


def _check_repository_names(criteria, annotations, index, entities):
    # Bypass check if no repo names were added/modified
    if not any(
        getattr(repo_name, '__lines__', None)
        for distro in (index or {}).values()
        for repos in (distro or {}).values()
        for repo_name in (repos or {}).keys()
    ):
        return

    recommendation = Recommendation.APPROVE
    problems = set()

    for distro_name, distro_file, repo_name in (
        (distro_name, distro_file, repo_name)
        for distro_name, distro in (index or {}).items()
        for distro_file, repos in (distro or {}).items()
        for repo_name in (repos or {}).keys()
    ):
        if not getattr(repo_name, '__lines__', None):
            continue

        for other_repo in entities.get(
            distro_name, {}
        ).get(repo_name, ()):
            if other_repo == repo_name:
                continue

            recommendation = Recommendation.DISAPPROVE
            problems.add(
                'Repository names must be unique across the distribution')
            annotations.append(Annotation(
                distro_file, repo_name.__lines__,
                f"This name is already used by the '{other_repo}' repository"))
            break

    if problems:
        message = '\n- '.join([
            'There are problems with the names of new repositories:',
        ] + sorted(problems))
    else:
        message = 'New repositories are named appropriately'

    criteria.append(Criterion(recommendation, message))


def _check_package_names(criteria, annotations, index, entities):
    # Bypass check if no packages were added/modified, and no release stanzas
    # were added/modified which might use the repository name as a package
    # name.
    if not any(
        any(getattr(package, '__lines__', None)
            for package in repo.get('release', {}).get('packages') or ()) or
        ((getattr(repo.get('release'), '__lines__', None) or
          getattr(repo_name, '__lines__', None)) and
         'release' in repo and not repo['release'].get('packages'))
        for distro in (index or {}).values()
        for repos in (distro or {}).values()
        for repo_name, repo in (repos or {}).items()
    ):
        return

    recommendation = Recommendation.APPROVE
    problems = set()

    for distro_name, distro_file, repo_name, repo in (
        (distro_name, distro_file, repo_name, repo)
        for distro_name, distro in (index or {}).items()
        for distro_file, repos in (distro or {}).items()
        for repo_name, repo in (repos or {}).items()
    ):
        release = repo.get('release')
        if not release:
            # Repository is not released, we don't know the package names
            continue

        packages = release.get('packages')
        if packages:
            # Repository has an explicit list of package names
            packages_to_check = [
                name for name in packages
                if getattr(name, '__lines__', None)
            ]
        elif getattr(release, '__lines__', None) or \
                getattr(repo_name, '__lines__', None):
            # Repository was just added or released and has in implicit
            # package name
            packages_to_check = [repo_name]
        else:
            # Released state of repository was not modified
            continue

        for package in packages_to_check:
            lines = (
                getattr(package, '__lines__', None) or
                getattr(release, '__lines__', None)
            )

            if (
                len(package) < 2 or
                not re.match(r'^[a-z][a-z0-9_]*$', package) or
                '__' in package
            ):
                recommendation = Recommendation.DISAPPROVE
                problems.add(
                    'Package names must comply with the mandatory rules of '
                    'REP 144')
                annotations.append(Annotation(
                    distro_file, lines,
                    f"The package name '{package}' does not comply with "
                    'the mandatory rules of REP 144'))

            for other_repo in entities.get(
                distro_name, {}
            ).get(package, ()):
                if other_repo == repo_name:
                    continue

                recommendation = Recommendation.DISAPPROVE
                problems.add(
                    'Package names must be unique across the distribution')
                annotations.append(Annotation(
                    distro_file, lines,
                    f"This name is already used by the '{other_repo}'"
                    'repository'))
                break

    if problems:
        message = '\n- '.join([
            'There are problems with the names of new packages:',
        ] + sorted(problems))
    else:
        message = 'New packages are named appropriately'

    criteria.append(Criterion(recommendation, message))


def _check_gbp_org(criteria, annotations, index):
    # This check only applies to rolling
    rolling_index = index.get('rolling', {})
    if not rolling_index:
        return

    # Bypass check if no release URLs were added/modified in rolling
    if not any(
        getattr(repo.get('release', {}).get('url'), '__lines__', None)
        for repos in rolling_index.values()
        for repo in repos.values()
    ):
        return

    recommendation = Recommendation.APPROVE
    problems = set()

    for distro_file, repo_name, repo in (
        (distro_file, repo_name, repo)
        for distro_file, repos in rolling_index.items()
        for repo_name, repo in repos.items()
    ):
        release = repo.get('release')
        if not release:
            continue

        url = release.get('url')
        if not getattr(url, '__lines__', None):
            continue

        if not (url or '').startswith('https://github.com/ros2-gbp/'):
            recommendation = Recommendation.DISAPPROVE
            problems.add(
                'Release repositories for rolling must be hosted in the '
                'ros2-gbp organization')
            annotations.append(Annotation(
                distro_file, url.__lines__,
                'This URL should start with '
                'https://github.com/ros2-gbp/'))

    if problems:
        message = '\n- '.join([
            'There are problems with release repository hosting:',
        ] + sorted(problems))
    else:
        message = 'New release repositories are hosted in the correct org'

    criteria.append(Criterion(recommendation, message))


def _check_bloom_version(criteria, annotations, index):
    # Only run if release version was updated
    if not any(
        getattr(repo.get('release', {}).get('version'), '__lines__', None)
        for distro in (index or {}).values()
        for repos in (distro or {}).values()
        for repo in (repos or {}).values()
    ):
        return

    event_path = os.environ.get(GITHUB_EVENT_PATH_ENVIRONMENT_VARIABLE.name)
    if not event_path or not Path(event_path).is_file():
        return

    try:
        with open(event_path, 'r') as f:
            event_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        criteria.append(Criterion(
            Recommendation.NEUTRAL,
            'Failed to parse GitHub event file'))
        return

    pull_request = event_data.get('pull_request', {})
    title = pull_request.get('title')
    if not (title or '').endswith('[bloom]'):
        return

    body = pull_request.get('body')
    match = re.search(r'bloom version:\s*`?([^\s`]+)`?', body or '')
    if not match:
        criteria.append(Criterion(
            Recommendation.NEUTRAL,
            'Could not verify Bloom version in PR body'))
        return

    bloom_version = match.group(1)
    bloom_ver_tuple = _parse_version(bloom_version)

    max_min_ver_tuple = max(MINIMUM_BLOOM_VERSIONS.values())
    max_min_version = '.'.join(map(str, max_min_ver_tuple))

    recommendation = Recommendation.APPROVE
    if bloom_ver_tuple < max_min_ver_tuple:
        recommendation = Recommendation.NEUTRAL

    for distro_name, distro in (index or {}).items():
        min_ver_tuple = MINIMUM_BLOOM_VERSIONS.get(distro_name, ())

        if bloom_ver_tuple < min_ver_tuple:
            recommendation = Recommendation.DISAPPROVE
        else:
            continue

        min_version = '.'.join(map(str, min_ver_tuple))
        for distro_file, repos in (distro or {}).items():
            for repo_name, repo in (repos or {}).items():
                release = repo.get('release', {})
                version_lines = getattr(
                    release.get('version'), '__lines__', None)
                if version_lines:
                    annotations.append(Annotation(
                        distro_file, version_lines,
                        f'Please run Bloom {min_version} or newer to '
                        f'release for {distro_name}. The PR was '
                        f'generated with {bloom_version}.'))

    if recommendation != Recommendation.APPROVE:
        message = f'Outdated Bloom version used - update to {max_min_version}'
    else:
        message = 'An up-to-date Bloom version was used'

    criteria.append(Criterion(recommendation, message))


def _check_multiple_releases(criteria, annotations, index):
    # Identify all modified release stanzas and their distributions
    releases = tuple(
        (distro_name, distro_file, repo['release'])
        for distro_name, distro in (index or {}).items()
        for distro_file, repos in (distro or {}).items()
        for repo in (repos or {}).values()
        if 'release' in repo and getattr(repo['release'], '__lines__', None)
    )

    if not releases:
        return

    distros_with_releases = {r[0] for r in releases}

    if len(distros_with_releases) > 1:
        recommendation = Recommendation.DISAPPROVE
        message = 'Changes to release stanzas across multiple distributions ' \
            'are not permitted'
        annotations.extend(
            Annotation(
                distro_file,
                getattr(release.get('version'), '__lines__', None) or
                getattr(release.get('url'), '__lines__', None) or
                release.__lines__,
                message)
            for _, distro_file, release in releases
        )
    else:
        recommendation = Recommendation.APPROVE
        message = 'Release changes are confined to a single distribution'

    criteria.append(Criterion(recommendation, message))


def _parse_github_repo_slug(url: str) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    clean_url = url.strip().rstrip('/')
    if clean_url.endswith('.git'):
        clean_url = clean_url[:-4]
    match = re.search(
        r'(?:^|[/@:])github\.com[:/]([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)$',
        clean_url,
        re.I,
    )
    if not match:
        return None
    owner, repo = match.groups()
    return f'{owner}/{repo}'


@lru_cache()
def _check_github_user_permission(
    submitting_user: str,
    repo_slug: str,
) -> Optional[str]:
    token = os.environ.get('GITHUB_TOKEN')
    try:
        from github import Auth
        from github import Github
    except ImportError:
        logger.warning('PyGithub is not installed')
        return None

    try:
        gh = Github(auth=Auth.Token(token)) if token else Github()
        repo = gh.get_repo(repo_slug)
        perm = repo.get_collaborator_permission(submitting_user)
        return perm.lower() if perm else None
    except Exception as e:  # noqa: B902
        logger.debug(
            f"Failed to check GitHub permissions for '{submitting_user}' "
            f"on '{repo_slug}': {e}")
        return None


def _get_pr_submitter_info() -> Optional[Tuple[str, bool]]:
    event_path = os.environ.get(GITHUB_EVENT_PATH_ENVIRONMENT_VARIABLE.name)
    if not event_path or not Path(event_path).is_file():
        return None

    try:
        with open(event_path, 'r', encoding='utf-8') as f:
            event_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    pull_request = event_data.get('pull_request') or {}
    submitting_user = (pull_request.get('user') or {}).get('login')
    if not submitting_user:
        sender = event_data.get('sender') or {}
        submitting_user = sender.get('login')

    if not submitting_user:
        return None

    repo_data = (
        event_data.get('repository') or
        (pull_request.get('base') or {}).get('repo') or
        {}
    )
    repo_url = repo_data.get('html_url') or ''
    if not _parse_github_repo_slug(repo_url):
        return None

    author_association = pull_request.get('author_association')
    is_distro_maintainer = author_association in (
        'MEMBER', 'OWNER', 'COLLABORATOR',
    )
    return submitting_user, is_distro_maintainer


def _check_repo_release_authorization(
    repo_name: str,
    repo: Dict[str, Any],
    full_repo: Dict[str, Any],
    submitting_user: str,
) -> Tuple[Optional[str], Optional[str], Any]:
    lines = (
        getattr(repo.get('release', {}).get('version'), '__lines__', None) or
        getattr(repo.get('release'), '__lines__', None) or
        getattr(repo_name, '__lines__', None) or
        getattr(repo, '__lines__', None)
    )

    release = (
        full_repo.get('release') if isinstance(full_repo, dict) else None
    )
    url = release.get('url') if isinstance(release, dict) else None

    if getattr(url, '__lines__', None) is not None:
        msg = (
            f"Authorization for repository '{repo_name}' could not be "
            'automatically verified (repository URL was added or modified)'
        )
        return None, msg, getattr(url, '__lines__', None) or lines

    slug = _parse_github_repo_slug(url) if isinstance(url, str) else None
    if not slug:
        msg = (
            f"Authorization for repository '{repo_name}' could not be "
            'automatically verified (target repository is not hosted on '
            'GitHub)'
        )
        return None, msg, lines

    perm = _check_github_user_permission(submitting_user, slug)
    if perm is None:
        msg = (
            f"Authorization for repository '{repo_name}' could not be "
            'automatically verified (failed to query GitHub permissions for '
            f"'{slug}')"
        )
        return None, msg, lines

    if perm not in ('admin', 'write', 'maintain'):
        problem = (
            f"User '{submitting_user}' is not authorized to modify "
            f"repository '{repo_name}'"
        )
        return problem, None, lines

    return None, None, None


def _check_maintainer_authorization(
    criteria: List[Criterion],
    annotations: List[Annotation],
    index: Dict[str, Any],
    full_index: Dict[str, Any],
) -> None:
    submitter_info = _get_pr_submitter_info()
    if not submitter_info:
        return

    submitting_user, is_distro_maintainer = submitter_info

    changed_repos = [
        (distro_file, repo_name, repo,
         (((full_index or {}).get(distro_name) or {}).get(
             distro_file) or {}).get(repo_name, repo))
        for distro_name, distro in (index or {}).items()
        for distro_file, repos in (distro or {}).items()
        for repo_name, repo in (repos or {}).items()
        if isinstance(repo.get('release'), dict)
    ]
    if not changed_repos:
        return

    if is_distro_maintainer:
        criteria.append(Criterion(
            Recommendation.APPROVE,
            'Maintainer authorization check passed for changed repositories'))
        return

    problems: Set[str] = set()
    unverified: Set[str] = set()

    for distro_file, repo_name, repo, full_repo in changed_repos:
        problem, unverified_msg, lines = _check_repo_release_authorization(
            repo_name, repo, full_repo, submitting_user)
        if problem:
            problems.add(problem)
            if lines:
                annotations.append(Annotation(
                    distro_file, lines,
                    f"User '@{submitting_user}' is not authorized to make "
                    f"changes to repository '{repo_name}'"))
        elif unverified_msg:
            unverified.add(unverified_msg)
            if lines:
                annotations.append(
                    Annotation(distro_file, lines, unverified_msg))

    if problems:
        recommendation = Recommendation.DISAPPROVE
        messages = sorted(problems)
        if unverified:
            messages.extend(sorted(unverified))
        message = '\n- '.join([
            'There are problems with maintainer authorization for '
            'changed repositories:',
        ] + messages)
    elif unverified:
        recommendation = Recommendation.NEUTRAL
        message = '\n- '.join([
            'Maintainer authorization could not be fully verified for '
            'changed repositories:',
        ] + sorted(unverified))
    else:
        recommendation = Recommendation.APPROVE
        message = (
            'Maintainer authorization check passed for changed repositories'
        )

    criteria.append(Criterion(recommendation, message))


def _read_index(
    path: Path,
    target_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    # 1. Read the rosdistro index
    if head_ref is not None:
        with Repo(path) as repo:
            tree = repo.tree(head_ref)
            if 'index-v4.yaml' not in tree:
                return None
            stream = GenericDecorator(
                tree['index-v4.yaml'].data_stream,
                name='index-v4.yaml')
            index = yaml.load(stream, yaml.SafeLoader)
    else:
        index_path = path / 'index-v4.yaml'
        if not index_path.is_file():
            return None
        with index_path.open('r') as f:
            stream = GenericDecorator(f, name='index-v4.yaml')
            index = yaml.load(stream, yaml.SafeLoader)
    if not index or not index.get('distributions'):
        return None

    # 2. Enumerate the files in each distribution
    all_dist_files = {
        dist_name:  [
            str(Path(dist_file))
            for dist_file in (dist.get('distribution') or [])
        ]
        for dist_name, dist in index['distributions'].items()
    }
    unique_dist_files = {
        file
        for files in all_dist_files.values()
        for file in files
    }

    # 3. Look for changes in each distribution file
    all_dist_changes = get_changed_yaml(
        path, list(unique_dist_files),
        target_ref=target_ref, head_ref=head_ref)
    if not all_dist_changes:
        return None

    return {
        dist_name: {
            dist_file: all_dist_changes[dist_file].get('repositories') or []
            for dist_file in dist_files
        } for dist_name, dist_files in all_dist_files.items()
    }


def _prune_index(changed_distros):
    for distro_name in tuple((changed_distros or {}).keys()):
        distro = changed_distros[distro_name]
        for distro_file in tuple((distro or {}).keys()):
            repos = distro[distro_file]
            prune_changed_yaml(repos)
            if not repos:
                del distro[distro_file]
        if not distro:
            del changed_distros[distro_name]


class RosdistroAnalyzer(ElementAnalyzerExtensionPoint):
    """Element analyzer for changes to ROS distribution files."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ElementAnalyzerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def analyze(  # noqa: D102
        self,
        path: Path,
        target_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
    ) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:
        criteria: List[Criterion] = []
        annotations: List[Annotation] = []

        # Read the full rosdistro index
        full_index = _read_index(path, target_ref, head_ref)
        if not full_index:
            # Bypass check if no distros were changed
            return None, None

        # Re-structure the index by "entity" names (repo and package names).
        # This can be used by checks to correlate changes across distributions
        # and repositories.
        entities: Dict[str, Dict[str, List[str]]] = {}
        for distro_name, distro in full_index.items():
            distro_entities = entities.setdefault(distro_name, {})
            for repos in (distro or {}).values():
                for repo_name, repo in (repos or {}).items():
                    distro_entities.setdefault(repo_name, []).append(repo_name)
                    release = repo.get('release')
                    if not release:
                        continue
                    for package in release.get('packages') or ():
                        distro_entities.setdefault(package, []).append(
                            repo_name)

        # Prune the index down to only changed elements
        index = copy.deepcopy(full_index)
        _prune_index(index)
        if not index:
            # Bypass check if no distros were changed
            return None, None

        logger.info('Performing analysis on ROS distribution changes...')

        _check_repository_names(criteria, annotations, index, entities)
        _check_package_names(criteria, annotations, index, entities)
        _check_gbp_org(criteria, annotations, index)
        _check_bloom_version(criteria, annotations, index)
        _check_multiple_releases(criteria, annotations, index)
        _check_maintainer_authorization(
            criteria, annotations, index, full_index)

        return criteria, annotations
