# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
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
    problems = set()

    # Names should be unique
    for distro_name, distro_file, repo_name, repo in (
        (distro_name, distro_file, repo_name, repo)
        for distro_name, distro in (index or {}).items()
        for distro_file, repos in (distro or {}).items()
        for repo_name, repo in (repos or {}).items()
    ):
        repo_url = repo.get('release', {}).get('url') or \
            repo.get('source', {}).get('url') or \
            repo.get('doc', {}).get('url') or \
            'unknown'

        entities_to_check = (
            name for name in
            (repo_name, *repo.get('release', {}).get('packages', []))
            if getattr(name, '__lines__', None)
        )
        for entity in entities_to_check:
            # Check for collisions across the entire index
            providers = entities.get(entity, {})

            # providers is {url -> [(distro, repo_name)]}
            other_providers = []
            for url, info_list in providers.items():
                for d_name, r_name in info_list:
                    if d_name == distro_name and r_name == repo_name:
                        # This is the current provider we are checking
                        continue

                    # Different repo name OR different URL is a collision
                    if r_name != repo_name or url != repo_url:
                        other_providers.append(f"'{r_name}' in {d_name}")

            if other_providers:
                recommendation = Recommendation.DISAPPROVE
                msg = f"The name '{entity}' is already used by: " + \
                      ', '.join(sorted(set(other_providers)))
                problems.add(msg)
                annotations.append(Annotation(
                    distro_file, entity.__lines__, msg))

    if problems:
        message = '\n- '.join(['There are problems with naming collision:'] +
                              sorted(problems))
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
        # Mapping: entity_name -> {repo_url -> [(distro_name, repo_name)]}
        entities: Dict[str, Dict[str, List[Tuple[str, str]]]] = {}
        for distro_name, distro in index.items():
            for repos in (distro or {}).values():
                for repo_name, repo in (repos or {}).items():
                    # Determine a unique identifier for the repository.
                    # We prefer the release URL, then the source URL.
                    repo_url = repo.get('release', {}).get('url') or \
                        repo.get('source', {}).get('url') or \
                        repo.get('doc', {}).get('url') or \
                        'unknown'

                    def add_entity(name):
                        distro_list = entities.setdefault(name, {}).setdefault(
                            repo_url, [])
                        distro_list.append((distro_name, repo_name))

                    add_entity(repo_name)
                    release = repo.get('release')
                    if release:
                        for package in release.get('packages') or ():
                            add_entity(package)

        # Prune the index down to only changed elements
        _prune_index(index)
        if not index:
            # Bypass check if no distros were changed
            return None, None

        logger.info('Performing analysis on ROS distribution changes...')

        _check_duplicates(criteria, annotations, index, entities)

        return criteria, annotations
