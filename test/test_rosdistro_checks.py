# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import itertools
import json
import os
from pathlib import Path
from typing import Iterable
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
    with index_path.open('w') as f:
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


# This particular violation needs a lot more context to validate
# It is explicitly tested here rather than using the VIOLATIONS list
def test_bloom_version_check(rosdistro_index_repo, tmp_path):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    # Create a release version update in "rolling" to trigger the check
    distros = {
        'rolling': {
            'existing_alpha': {
                'release': {
                    'version': '1.0.0-1',
                }
            }
        }
    }
    merged_distros = _merge_distributions(EXISTING_DISTROS, distros)
    for distro_name, repos in merged_distros.items():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('w') as f:
            yaml.dump({'repositories': repos}, f)

    index_path = repo_dir / 'index-v4.yaml'
    with index_path.open('w') as f:
        yaml.dump(_generate_index(merged_distros.keys()), f)

    # Test 1: No PR event path -> should return None, None
    with patch.dict(os.environ):
        os.environ.pop('GITHUB_EVENT_PATH', None)
        criteria, annotations = extension.analyze(repo_dir)
        # The duplicate check should pass
        assert criteria is not None
        assert not any('Bloom version' in c.rationale for c in criteria)

    event_data = {
        'pull_request': {
            'title': 'Release my_repo [bloom]',
            'body': 'bloom version: 0.10.0',
        }
    }
    event_path = tmp_path / 'event.json'

    with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event_path)}):
        # Test 2: Invalid PR title -> no bloom check
        event_data['pull_request']['title'] = 'Release my_repo'
        with event_path.open('w') as f:
            json.dump(event_data, f)

        criteria, annotations = extension.analyze(repo_dir)
        assert not any('Bloom version' in c.rationale for c in criteria)

        # Test 3: Valid PR title but old bloom version -> DISAPPROVE or NEUTRAL
        event_data['pull_request']['title'] = 'Release my_repo [bloom]'
        with event_path.open('w') as f:
            json.dump(event_data, f)

        criteria, annotations = extension.analyze(repo_dir)
        bloom_c = [c for c in criteria if 'Bloom version' in c.rationale]
        assert len(bloom_c) == 1
        assert bloom_c[0].recommendation == Recommendation.DISAPPROVE
        assert any('Please run Bloom' in a.message for a in annotations)

        # Test 4: Up-to-date bloom version -> APPROVE
        event_data['pull_request']['body'] = 'bloom version: 0.15.0'
        with event_path.open('w') as f:
            json.dump(event_data, f)

        criteria, annotations = extension.analyze(repo_dir)
        bloom_c = [c for c in criteria if 'Bloom version' in c.rationale]
        assert len(bloom_c) == 1
        assert bloom_c[0].recommendation == Recommendation.APPROVE
        assert not any(
            'Please run Bloom' in a.message for a in annotations)

        # Test 5: Failure to parse Bloom version from PR body -> NEUTRAL
        event_data['pull_request']['body'] = 'no version here'
        with event_path.open('w') as f:
            json.dump(event_data, f)

        criteria, annotations = extension.analyze(repo_dir)
        bloom_c = [
            c for c in criteria
            if 'Could not verify Bloom version' in c.rationale]
        assert len(bloom_c) == 1
        assert bloom_c[0].recommendation == Recommendation.NEUTRAL

        # Test 6: Failure to parse the event file (invalid JSON) -> NEUTRAL
        with event_path.open('w') as f:
            f.write('not a json')

        criteria, annotations = extension.analyze(repo_dir)
        bloom_c = [
            c for c in criteria
            if 'Failed to parse GitHub event file' in c.rationale]
        assert len(bloom_c) == 1
        assert bloom_c[0].recommendation == Recommendation.NEUTRAL
