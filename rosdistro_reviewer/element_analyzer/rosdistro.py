# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

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

logger = colcon_logger.getChild(__name__)


class ManifestCheck:
    """Base class for checks performed on ROS package manifests."""

    def check(self, pxml_path: str, pxml_content: str) -> List[str]:
        """
        Perform a check on a package manifest.

        :param pxml_path: Path to the package.xml file
        :param pxml_content: Content of the package.xml file
        :return: A list of error messages, or an empty list if no issues found
        """
        raise NotImplementedError()


class REP144Check(ManifestCheck):
    """Check if the package name follows REP-144."""

    def check(self, pxml_path: str, pxml_content: str) -> List[str]:
        name_match = re.search(r'<name>(.*?)</name>', pxml_content)
        if name_match:
            pkg_name = name_match.group(1)
            if not _is_rep144_compliant(pkg_name):
                return [f"Package '{pkg_name}' does not follow REP-144"]
        return []


class LicenseTagCheck(ManifestCheck):
    """Check if the package has at least one license tag."""

    def check(self, pxml_path: str, pxml_content: str) -> List[str]:
        if not re.search(r'<license(>| .*?>)', pxml_content):
            return ['Missing <license> tag in package.xml']
        return []


def _check_duplicates(criteria, annotations, index, entities):
    # Bypass check if no repo or package names were added/modified
    if not any(
        getattr(repo_name, '__lines__', None) or any(
            getattr(package, '__lines__', None)
            for package in repo.get('release', {}).get('packages', ())
        )
        for distro in (index or {}).values()
        for repos in (distro or {}).values()
        for repo_name, repo in (repos or {}).items()
    ):
        return

    recommendation = Recommendation.APPROVE

    # Names should be unique
    for distro_name, distro_file, repo_name, repo in (
        (distro_name, distro_file, repo_name, repo)
        for distro_name, distro in (index or {}).items()
        for distro_file, repos in (distro or {}).items()
        for repo_name, repo in (repos or {}).items()
    ):
        entities_to_check = (
            name for name in
            (repo_name, *repo.get('release', {}).get('packages', []))
            if getattr(name, '__lines__', None)
        )
        for entity in entities_to_check:
            for other_repo in entities.get(distro_name, {}).get(entity, ()):
                if other_repo == repo_name:
                    continue

                recommendation = Recommendation.DISAPPROVE
                annotations.append(Annotation(
                    distro_file, entity.__lines__,
                    'This name is already used by the '
                    f"'{other_repo}' repository"))
                break

    if recommendation != Recommendation.APPROVE:
        message = 'There are problems with naming collision'
    else:
        message = 'New packages and repositories have unique names'

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
            index = yaml.load(
                        tree['index-v4.yaml'].data_stream,
                        yaml.SafeLoader)
    else:
        index_path = path / 'index-v4.yaml'
        if not index_path.is_file():
            return None
        with index_path.open('r') as f:
            index = yaml.load(f, yaml.SafeLoader)
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


def _is_rep144_compliant(name: str) -> bool:
    return bool(re.match(r'^[a-z][a-z0-9_]*$', name))


def _is_any_modified(data: Any) -> bool:
    if getattr(data, '__lines__', None) is not None:
        return True
    if isinstance(data, dict):
        for k, v in data.items():
            if _is_any_modified(k) or _is_any_modified(v):
                return True
    elif isinstance(data, list):
        for item in data:
            if _is_any_modified(item):
                return True
    return False


def _validate_markdown(content: str) -> None:
    """Ensure generated markdown is structurally sound."""
    # Check for balanced backticks
    if len(re.findall(r'(?<!`)`(?!`)', content)) % 2 != 0:
        raise ValueError('Unbalanced single backticks in markdown')
    if len(re.findall(r'```', content)) % 2 != 0:
        raise ValueError('Unbalanced triple backticks in markdown')


def _check_source_repositories(
    criteria: List[Criterion],
    annotations: List[Annotation],
    index: Dict[str, Any],
    manifest_checks: List[ManifestCheck]
) -> None:
    """
    Check source repositories for common issues.

    This function clones repositories that were modified or added,
    and runs a suite of checks on their contents.
    """
    problems = set()
    recommendation = Recommendation.APPROVE

    for distro_name, distro in (index or {}).items():
        for distro_file, repos in (distro or {}).items():
            for repo_name, repo in (repos or {}).items():
                source = repo.get('source')
                if not source or source.get('type') != 'git':
                    continue

                if not _is_any_modified(repo_name) and \
                   not _is_any_modified(repo):
                    continue

                url = source.get('url')
                version = source.get('version', 'master')
                if not url:
                    continue

                logger.info(f'Checking source repository: {url}')
                temp_dir = tempfile.mkdtemp()
                try:
                    subprocess.run(
                        ['git', 'clone', '--depth', '1', '-b',
                         version, url, temp_dir],
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    # Check for LICENSE file
                    has_license = False
                    for f in os.listdir(temp_dir):
                        if f.lower() in [
                            'license', 'license.txt', 'license.md', 'copying'
                        ]:
                            has_license = True
                            break
                    if not has_license:
                        recommendation = min(
                            recommendation, Recommendation.NEUTRAL)
                        problems.add(
                            f"New repository '{repo_name}' is "
                            'missing a LICENSE file')
                        annotations.append(
                            Annotation(
                                distro_file, repo_name.__lines__,
                                'Missing LICENSE file in source repo')
                        )

                    # Run manifest-based checks
                    package_xmls_found = False
                    for root, _, files in os.walk(temp_dir):
                        if 'package.xml' in files:
                            package_xmls_found = True
                            pxml_path = os.path.join(root, 'package.xml')
                            try:
                                with open(pxml_path, 'r') as f:
                                    content = f.read()
                                    for check in manifest_checks:
                                        errors = check.check(
                                            pxml_path, content)
                                        for err in (errors or []):
                                            recommendation = min(
                                                recommendation,
                                                Recommendation.NEUTRAL)
                                            problems.add(
                                                f"{err} in '{repo_name}'")
                                            annotations.append(
                                                Annotation(
                                                    distro_file,
                                                    repo_name.__lines__,
                                                    err))
                            except Exception as e:
                                logger.error(
                                    f'Error checking {pxml_path}: {e}')

                    if not package_xmls_found:
                        recommendation = min(
                            recommendation, Recommendation.NEUTRAL)
                        problems.add(
                            f"New repository '{repo_name}' does not contain "
                            'any ROS packages (missing package.xml)')
                        annotations.append(
                            Annotation(
                                distro_file, repo_name.__lines__,
                                'No package.xml found in source repo'))

                except subprocess.SubprocessError as e:
                    logger.error(f'Error cloning {url}: {e}')
                    recommendation = min(
                        recommendation, Recommendation.NEUTRAL)
                    problems.add(
                        f"Could not clone repository '{repo_name}': {e}")
                finally:
                    shutil.rmtree(temp_dir)

    if problems:
        message = '\n- '.join(
            ['There are problems with new package submissions:'] +
            sorted(problems))
    else:
        message = 'New package submissions follow guidelines'

    _validate_markdown(message)
    criteria.append(Criterion(recommendation, message))


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
        index = _read_index(path, target_ref, head_ref)
        if not index:
            # Bypass check if no distros were changed
            return None, None

        # Re-structure the index by "entity" names (repo and package names).
        # This can be used by checks to correlate changes across distributions
        # and repositories.
        entities: Dict[str, Dict[str, List[str]]] = {}
        for distro_name, distro in index.items():
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
        _prune_index(index)
        if not index:
            # Bypass check if no distros were changed
            return None, None

        logger.info('Performing analysis on ROS distribution changes...')

        _check_duplicates(criteria, annotations, index, entities)
        
        _check_source_repositories(
            criteria, annotations, index, 
            [REP144Check(), LicenseTagCheck()])

        return criteria, annotations
