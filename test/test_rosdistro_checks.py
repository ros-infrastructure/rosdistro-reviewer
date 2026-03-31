# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import itertools
import os
from pathlib import Path
from typing import Iterable
from unittest.mock import MagicMock
from unittest.mock import patch

from git import Repo
import pytest
from rosdistro_reviewer.element_analyzer.rosdistro import RosdistroAnalyzer
from rosdistro_reviewer.review import Recommendation
import yaml


def _generate_index(distro_names):
    return {
        'distributions': {
            distro_name: {
                'distribution': [distro_name + '/distribution.yaml'],
                'distribution_cache': None,
                'distribution_status': 'active',
                'distribution_type': 'ros2',
                'python_version': 3,
            } for distro_name in distro_names
        },
        'type': 'index',
        'version': 4,
    }


@pytest.fixture
def rosdistro_index_repo(empty_repo) -> Iterable[Repo]:
    repo_dir = Path(empty_repo.working_tree_dir)

    for distro_name, repos in EXISTING_DISTROS.items():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('w') as f:
            yaml.dump({'repositories': repos}, f)

        empty_repo.index.add(str(file_path))

    index_path = repo_dir / 'index-v4.yaml'
    with index_path.open('r' if index_path.exists() else 'w') as f:
        yaml.dump(_generate_index(EXISTING_DISTROS.keys()), f)

    empty_repo.index.add(str(index_path))
    empty_repo.index.commit('Add distribution files')

    return empty_repo


def test_no_files(empty_repo):
    repo_dir = Path(empty_repo.working_tree_dir)
    extension = RosdistroAnalyzer()
    assert (None, None) == extension.analyze(repo_dir)


def test_no_changes(rosdistro_index_repo):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()
    assert (None, None) == extension.analyze(repo_dir)


def _all_combinations(iterable):
    for r in range(1, 3):
        yield from itertools.combinations(iterable, r)


def _merge_distributions(first, second):
    if isinstance(first, dict):
        assert isinstance(second, dict)
        result = dict(first)
        for k, v in second.items():
            if k not in result:
                result[k] = v
            else:
                result[k] = _merge_distributions(result[k], v)
        return result
    elif isinstance(first, list):
        assert isinstance(second, list)
        result = []
        for v in first:
            try:
                i = second.index(v)
            except ValueError:
                result.append(v)
            else:
                result.append(_merge_distributions(v, second[i]))
        for v in second:
            if v not in result:
                result.append(v)
        return result
    else:
        assert first == second
        return first


def _merge_all_distros(distros_list):
    result = {}
    for distros in distros_list:
        result = _merge_distributions(result, distros)
    return result


# These repos are already committed to the index and aren't part of the change.
# They must be syntactically correct, but do not necessarily need to pass the
# checks.
EXISTING_DISTROS = {
    'rolling': {
        'existing_alpha': {
            'source': {
                'type': 'git',
                'url': 'https://example.com/existing_alpha.git',
                'version': 'main',
            },
        },
    },
}


# These are the "control" repo changes for rosdistro check validation.
# Each one must pass all checks and be syntactically correct.
CONTROL_DISTROS = {
    'rolling': {
        'control_bravo': {
            'source': {
                'type': 'git',
                'url': 'https://example.com/control_bravo.git',
                'version': 'main',
            },
        },
    },
}


@pytest.fixture(autouse=True)
def mock_subprocess():
    with patch(
        'rosdistro_reviewer.element_analyzer.rosdistro.subprocess.run'
    ) as mock_run:
        def default_side_effect(cmd, **kwargs):
            if cmd[0] == 'git' and cmd[1] == 'clone':
                dest = cmd[7]
                os.makedirs(dest, exist_ok=True)
                with open(os.path.join(dest, 'package.xml'), 'w') as f:
                    f.write('<package><name>valid_package</name></package>')
            return MagicMock()
        mock_run.side_effect = default_side_effect
        yield mock_run


def test_manifest_base_orchestration(rosdistro_index_repo, mock_subprocess):
    from rosdistro_reviewer.element_analyzer.rosdistro import \
        _check_source_repositories, ManifestCheck
    from rosdistro_reviewer.review import Recommendation

    class SimpleCheck(ManifestCheck):
        def check(self, pxml_path, pxml_content):
            if 'fail' in pxml_content:
                return ['Found failure string']
            return []

    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    
    # Simulate a new repo
    class AnnotatedStr(str): pass
    repo_name = AnnotatedStr('new_repo')
    repo_name.__lines__ = range(1, 2)
    
    index = {
        'rolling': {
            'rolling/distribution.yaml': {
                repo_name: {
                    'source': {
                        'type': 'git',
                        'url': 'https://example.com/new_repo.git',
                        'version': 'main'
                    }
                }
            }
        }
    }

    criteria = []
    annotations = []

    # Mock git clone to provide a 'fail' manifest
    def side_effect(cmd, **kwargs):
        dest = cmd[7]
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, 'package.xml'), 'w') as f:
            f.write('<package>fail</package>')
        return MagicMock()
    mock_subprocess.side_effect = side_effect

    _check_source_repositories(criteria, annotations, index, [SimpleCheck()])
    
    assert any('Found failure string' in c.rationale for c in criteria)
    assert any(a.message == 'Found failure string' for a in annotations)


# This is a list of violations to check for.
# To avoid collisions, each check should use unique repo names.
VIOLATIONS = {
    '*': CONTROL_DISTROS,
    'A': {
        # This repo has packages with a naming collision
        'rolling': {
            'charlie': {
                'release': {
                    'packages': ['existing_alpha'],
                },
            },
        },
    },
    'B': {
        # These repos have packages which conflict with each other
        'rolling': {
            'delta': {
                'release': {
                    'packages': ['duplicate_name'],
                },
            },
            'echo': {
                'release': {
                    'packages': ['duplicate_name'],
                },
            },
        },
    },
}


def pytest_generate_tests(metafunc):
    if 'violation_distros' not in metafunc.fixturenames:
        return
    combinations = {
        ''.join(key_set): _merge_all_distros(map(VIOLATIONS.get, key_set))
        for key_set in _all_combinations(sorted(VIOLATIONS.keys()))
        if key_set != ('*',)
    }
    metafunc.parametrize(
        'violation_distros',
        combinations.values(),
        ids=combinations.keys())


def test_control(rosdistro_index_repo):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    distros = _merge_distributions(EXISTING_DISTROS, CONTROL_DISTROS)
    for distro_name, repos in distros.items():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('w') as f:
            yaml.dump({'repositories': repos}, f)

    index_path = repo_dir / 'index-v4.yaml'
    with index_path.open('w') as f:
        yaml.dump(_generate_index(distros.keys()), f)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria is not None and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)


def test_removal_only(rosdistro_index_repo):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    for distro_name in EXISTING_DISTROS.keys():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('w') as f:
            yaml.dump({'repositories': {}}, f)

    assert (None, None) == extension.analyze(repo_dir)


def test_violation(rosdistro_index_repo, violation_distros):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    distros = _merge_distributions(EXISTING_DISTROS, violation_distros)
    for distro_name, repos in distros.items():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('w') as f:
            yaml.dump({'repositories': repos}, f)

    index_path = repo_dir / 'index-v4.yaml'
    with index_path.open('w') as f:
        yaml.dump(_generate_index(distros.keys()), f)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)
