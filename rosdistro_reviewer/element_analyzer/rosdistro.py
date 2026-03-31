# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from catkin_pkg.package import parse_package_string
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from git import Repo
from rosdistro import get_distribution_cache
from rosdistro import get_index
from rosdistro import get_index_url
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

    result = {
        dist_name: {
            dist_file: all_dist_changes[dist_file].get('repositories') or []
            for dist_file in dist_files
        } for dist_name, dist_files in all_dist_files.items()
    }
    return result


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


def _check_version_bumps(criteria, annotations, index):
    recommendation = Recommendation.APPROVE
    bumps = set()

    for distro in (index or {}).values():
        for repos in (distro or {}).values():
            for repo_name, repo in (repos or {}).items():
                # If repo_name itself is added, it is a new package, not a bump
                if getattr(repo_name, '__lines__', None):
                    continue

                release = repo.get('release')
                if not release:
                    continue

                version = release.get('version')
                # If version is modified
                if getattr(version, '__lines__', None):
                    # Check if ANYTHING ELSE in this repo was modified
                    # We want to isolate "simple" bumps.
                    other_modified = False
                    for k, v in repo.items():
                        if k == 'release':
                            for rk, rv in v.items():
                                if rk != 'version' and \
                                   getattr(rv, '__lines__', None):
                                    other_modified = True
                                    break
                        elif getattr(v, '__lines__', None):
                            other_modified = True
                            break
                        if other_modified:
                            break

                    if not other_modified:
                        bumps.add(repo_name)

    if bumps:
        message = 'The following repositories have simple version bumps: ' + \
                  ', '.join(sorted(bumps))
        criteria.append(Criterion(Recommendation.APPROVE, message))


def _find_cycles(graph: Dict[str, Set[str]]) -> List[List[str]]:
    cycles = []
    visited = set()
    path = []
    path_set = set()

    def visit(node):
        if node in path_set:
            # Found a cycle! Extract it from the path.
            idx = path.index(node)
            cycles.append(path[idx:] + [node])
            return
        if node in visited:
            return

        visited.add(node)
        path.append(node)
        path_set.add(node)

        for neighbor in graph.get(node, []):
            visit(neighbor)

        path_set.remove(node)
        path.pop()

    for node in graph:
        visit(node)
    return cycles


def _check_dependency_cycles(criteria, annotations, index):
    if not index:
        return

    # We only check for cycles in the distributions that were changed
    for distro_name, distro_data in index.items():
        logger.info(f'Checking for dependency cycles in {distro_name}...')

        # Load the distribution cache
        try:
            ros_index = get_index(get_index_url())
            cache = get_distribution_cache(ros_index, distro_name)
        except Exception as e:
            logger.warning(f'Could not load cache for {distro_name}: {e}')
            continue

        # Build dependency graph from cache
        graph = {}
        for pkg_name, xml in cache.release_package_xmls.items():
            try:
                pkg = parse_package_string(xml)
                # We consider all dependency types for cycle detection
                deps = set()
                deps.update(d.name for d in pkg.build_depends)
                deps.update(d.name for d in pkg.buildtool_depends)
                deps.update(d.name for d in pkg.run_depends)
                deps.update(d.name for d in pkg.test_depends)
                deps.update(d.name for d in pkg.exec_depends)
                deps.update(d.name for d in pkg.doc_depends)
                graph[pkg_name] = deps
            except Exception:
                continue

        # Identify which packages were changed/added in this PR
        changed_pkgs = set()
        for distro_file, repos in distro_data.items():
            if not isinstance(repos, dict):
                continue
            for repo_name, repo in repos.items():
                release = repo.get('release')
                if release:
                    changed_pkgs.update(release.get('packages') or [])

        # Find cycles
        cycles = _find_cycles(graph)

        # Filter cycles to only those involving changed packages
        relevant_cycles = []
        for cycle in cycles:
            if any(node in changed_pkgs for node in cycle):
                relevant_cycles.append(cycle)

        if relevant_cycles:
            recommendation = Recommendation.DISAPPROVE
            problems = []
            for cycle in relevant_cycles:
                cycle_str = ' -> '.join(cycle)
                problems.append(f'Dependency cycle detected: {cycle_str}')

            message = '\n- '.join(['There are dependency cycles:'] + problems)
            criteria.append(Criterion(recommendation, message))
        else:
            criteria.append(Criterion(
                Recommendation.APPROVE,
                f'No dependency cycles detected in {distro_name}'))


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

        logger.info('Performing analysis on ROS distribution changes...')

        # Prune the index down to only changed elements
        _prune_index(index)
        if not index:
            # Bypass check if no distros were changed
            return None, None

        _check_dependency_cycles(criteria, annotations, index)
        _check_duplicates(criteria, annotations, index, entities)
        _check_version_bumps(criteria, annotations, index)

        return criteria, annotations
