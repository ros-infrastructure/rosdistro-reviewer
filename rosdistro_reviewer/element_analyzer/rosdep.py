# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from git import Repo
from git.objects import Blob
from git.objects import Tree
from rosdep2 import create_default_installer_context
from rosdistro_reviewer.element_analyzer \
    import ElementAnalyzerExtensionPoint
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation
from rosdistro_reviewer.yaml_changes import get_changed_yaml
from rosdistro_reviewer.yaml_changes import prune_changed_yaml

logger = colcon_logger.getChild(__name__)

EOL_PLATFORMS = {
    'debian': {
        'lenny',
        'squeeze',
        'wheezy',
        'jessie',
        'stretch',
        'buster',
    },
    'fedora': {
        str(n) for n in range(21, 39)
    },
    'rhel': {
        str(n) for n in range(3, 8)
    },
    'ubuntu': {
        'trusty',
        'utopic',
        'vivid',
        'wily',
        'xenial',
        'yakkety',
        'zesty',
        'artful',
        'bionic',
        'cosmic',
        'disco',
        'eoan',
        'groovy',
        'hirsute',
        'impish',
        'kinetic',
        'lunar',
        'mantic',
    },
}


def _check_key_names(criteria, annotations, changed_rosdeps, key_counts):
    # Bypass check if no new keys were added
    if not any(
        getattr(key, '__lines__', None)
        for changes in changed_rosdeps.values()
        for key in changes.keys()
    ):
        return

    recommendation = Recommendation.APPROVE
    problems = set()

    # Pip-only rules should end in -pip
    for file, changes in changed_rosdeps.items():
        if Path(file).name != 'python.yaml':
            continue
        for k, v in changes.items():
            if not getattr(k, '__lines__', None):
                continue

            pip_only = all(
                isinstance(rule, dict) and set(rule.keys()) == {'pip'}
                for rule in v.values())
            if pip_only != k.endswith('-pip'):
                recommendation = Recommendation.DISAPPROVE
                problems.add(
                    "Keys which contain only pip rules should end in '-pip'")
                annotations.append(Annotation(
                    file,
                    k.__lines__,
                    f"This key should{'' if pip_only else ' not'} "
                    "end in '-pip'"))

    # Python keys should go in python.yaml
    for file, changes in changed_rosdeps.items():
        if Path(file).name == 'python.yaml':
            continue
        for key in changes.keys():
            if not getattr(key, '__lines__', None):
                continue

            if key.startswith('python'):
                recommendation = Recommendation.DISAPPROVE
                problems.add(
                    "Keys for Python packages should go in 'python.yaml'")
                annotations.append(Annotation(
                    file, key.__lines__, 'This key belongs in python.yaml'))

    # Key names SHOULD match the ubuntu apt package name
    for file, changes in changed_rosdeps.items():
        for key, rules in changes.items():
            if not getattr(key, '__lines__', None):
                continue
            ubuntu_rule = rules.get('ubuntu', {})
            if isinstance(ubuntu_rule, dict) and '*' in ubuntu_rule:
                ubuntu_rule = ubuntu_rule['*']
            if isinstance(ubuntu_rule, dict):
                if 'apt' not in ubuntu_rule:
                    continue
                ubuntu_rule = ubuntu_rule['apt']
                if isinstance(ubuntu_rule, dict) and 'packages' in ubuntu_rule:
                    ubuntu_rule = ubuntu_rule['packages']
            if not ubuntu_rule:
                continue
            if key not in ubuntu_rule:
                recommendation = min(recommendation, Recommendation.NEUTRAL)
                problems.add(
                    'New key names should typically match the Ubuntu '
                    'package name')
                annotations.append(Annotation(
                    file,
                    key.__lines__,
                    'This key does not match the Ubuntu package name'))

    # Keys should not be defined in multiple places
    for file, changes in changed_rosdeps.items():
        for key in changes.keys():
            if not getattr(key, '__lines__', None):
                continue
            if key_counts.get(key, 0) > 1:
                recommendation = Recommendation.DISAPPROVE
                problems.add(
                    'Keys names should be unique across the entire database')
                annotations.append(Annotation(
                    file, key.__lines__, 'This key is also defined elsewhere'))

    if problems:
        message = '\n- '.join([
            'There are problems with the names of new rosdep keys:',
        ] + sorted(problems))
    else:
        message = 'New rosdep keys are named appropriately'

    criteria.append(Criterion(recommendation, message))


def _check_platforms(criteria, annotations, changed_rosdeps):
    # Bypass check if no platforms were added
    if not any(
        os != '*' and (getattr(os, '__lines__', None) or (
            isinstance(rule, dict) and any(
                getattr(release, '__lines__', None) and release != '*'
                for release in rule.keys()
            )
        ))
        for changes in changed_rosdeps.values()
        for rules in changes.values()
        for os, rule in rules.items()
    ):
        return

    recommendation = Recommendation.APPROVE
    problems = set()

    installer_context = create_default_installer_context()
    os_keys = {'*'}.union(installer_context.get_os_keys())

    # New explicit rules for EOL platforms are not allowed
    # New rules for unsupported OSs are not allowed
    for file, changes in changed_rosdeps.items():
        for rules in changes.values():
            for os, rule in rules.items():
                if os not in os_keys and getattr(os, '__lines__', None):
                    recommendation = Recommendation.DISAPPROVE
                    problems.add(
                        'One or more explicitly provided platforms are not '
                        'supported by rosdep')
                    annotations.append(Annotation(
                        file, os.__lines__,
                        'This OS is not supported by rosdep'))
                elif isinstance(rule, dict):
                    eol_releases = EOL_PLATFORMS.get(os, set())
                    for release in rule.keys():
                        if release not in eol_releases or not getattr(
                            release, '__lines__', None,
                        ):
                            continue
                        recommendation = Recommendation.DISAPPROVE
                        problems.add(
                            'One or more explicitly provided platforms are '
                            'no longer supported')
                        annotations.append(Annotation(
                            file, release.__lines__,
                            'This release is no longer a supported '
                            f'version of {os}'))

    if problems:
        message = '\n- '.join([
            'There are problems with explicitly provided platforms:',
        ] + sorted(problems))
    else:
        message = 'Platforms for new rosdep rules are valid'

    criteria.append(Criterion(recommendation, message))


def _check_installers(criteria, annotations, changed_rosdeps):
    # Bypass check if no explicit installers were added
    if not any(
        os != '*' and isinstance(rule, dict) and any(
            isinstance(sub_rule, dict) and any(
                getattr(installer, '__lines__', None)
                for installer in sub_rule.keys()
            )
            for sub_rule in rule.values()
        )
        for changes in changed_rosdeps.values()
        for rules in changes.values()
        for os, rule in rules.items()
    ):
        return

    recommendation = Recommendation.APPROVE
    problems = set()

    installer_context = create_default_installer_context()

    for file, changes in changed_rosdeps.items():
        for rules in changes.values():
            for os, rule in rules.items():
                if os == '*' or not isinstance(rule, dict):
                    continue
                try:
                    os_installers = installer_context.get_os_installer_keys(os)
                except KeyError:
                    continue
                for key, sub_rule in rule.items():
                    if not isinstance(sub_rule, dict):
                        continue
                    if 'packages' in sub_rule:
                        if not getattr(key, '__lines__', None):
                            continue
                        if key in os_installers:
                            continue
                        recommendation = Recommendation.DISAPPROVE
                        problems.add(
                            'One or more explicitly provided installer is not '
                            'supported by rosdep')
                        annotations.append(Annotation(
                            file,
                            range(
                                key.__lines__.start,
                                sub_rule.__lines__.stop),
                            f"Installer '{key}' is not supported for '{os}'"))
                        continue
                    for installer, sub_sub_rule in sub_rule.items():
                        if not getattr(installer, '__lines__', None):
                            continue
                        if installer in os_installers:
                            continue
                        recommendation = Recommendation.DISAPPROVE
                        problems.add(
                            'One or more explicitly provided installer is not '
                            'supported by rosdep')
                        annotations.append(Annotation(
                            file,
                            range(
                                installer.__lines__.start,
                                sub_sub_rule.__lines__.stop),
                            f"Installer '{installer}' is not supported "
                            f"for '{os}'"))

    if problems:
        message = '\n- '.join([
            'There are problems with explicitly provided installers:',
        ] + sorted(problems))
    else:
        message = 'Installers for new rosdep rules are valid'

    criteria.append(Criterion(recommendation, message))


def _is_yaml_blob(item, depth) -> bool:
    return PurePosixPath(item.path).suffix == '.yaml'


def _get_changed_rosdeps(
    path: Path,
    target_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> Tuple[Optional[Dict[str, int]], Optional[Dict[str, Any]]]:
    if head_ref:
        with Repo(path) as repo:
            tree = repo.tree(head_ref)
            try:
                tree = tree['rosdep']
            except KeyError:
                return None, None
            if not isinstance(tree, Tree):
                return None, None
            rosdep_files = [
                str(Path(item.path))
                for item in tree.traverse(predicate=_is_yaml_blob)
                if isinstance(item, Blob)
            ]
    else:
        rosdep_files = [
            str(p.relative_to(path))
            for p in path.glob('rosdep/*.yaml')
        ]
    if not rosdep_files:
        logger.info('No rosdep files were found in the repository')
        return None, None

    changes = get_changed_yaml(
        path, rosdep_files, target_ref=target_ref, head_ref=head_ref)
    if not changes:
        logger.info('No rosdep files were modified')
        return None, None

    rosdep_changes = {}
    key_counts: Dict[str, int] = {}
    for rosdep_file, data in changes.items():
        if data:
            for key in data.keys():
                key_counts.setdefault(key, 0)
                key_counts[key] += 1
            prune_changed_yaml(data)
        if data:
            rosdep_changes[rosdep_file] = data

    return key_counts, rosdep_changes


class RosdepAnalyzer(ElementAnalyzerExtensionPoint):
    """Element analyzer for changes to the rosdep database."""

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

        key_counts, changed_rosdeps = _get_changed_rosdeps(
            path, target_ref, head_ref)
        if not changed_rosdeps:
            # Bypass check if no rosdeps were changed
            return None, None

        logger.info('Performing analysis on rosdep changes...')

        _check_key_names(criteria, annotations, changed_rosdeps, key_counts)
        _check_platforms(criteria, annotations, changed_rosdeps)
        _check_installers(criteria, annotations, changed_rosdeps)

        return criteria, annotations
