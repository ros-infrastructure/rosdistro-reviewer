# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import itertools
import json
import os
from pathlib import Path
import re
from typing import Iterable
from unittest.mock import patch

from git import Repo
import pytest
import responses
from rosdistro_reviewer.element_analyzer.rosdistro import RosdistroAnalyzer
from rosdistro_reviewer.git_lines import get_added_lines
from rosdistro_reviewer.review import Recommendation
from rosdistro_reviewer.yaml_changes import get_changed_yaml
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


def _write_distributions(distros, repo_dir):
    for distro_name, repos in distros.items():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('w') as f:
            yaml.dump({'repositories': repos}, f)

    index_path = repo_dir / 'index-v4.yaml'
    with index_path.open('w') as f:
        yaml.dump(_generate_index(distros.keys()), f)

    return index_path


@pytest.fixture
def mock_github_event(tmp_path_factory):
    event_dir = tmp_path_factory.mktemp('github_event')
    event_path = event_dir / 'event.json'
    event_data = {
        'pull_request': {
            'user': {
                'login': 'some-user',
            },
            'author_association': 'MEMBER',
            'base': {
                'repo': {
                    'html_url': 'https://github.com/ros/rosdistro',
                    'full_name': 'ros/rosdistro',
                },
            },
        },
    }
    with event_path.open('w') as f:
        json.dump(event_data, f)
    with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event_path)}):
        yield event_path


@pytest.fixture
def mock_github_non_member_event(tmp_path_factory):
    event_dir = tmp_path_factory.mktemp('github_non_member_event')
    event_path = event_dir / 'event.json'
    event_data = {
        'pull_request': {
            'user': {
                'login': 'some-user',
            },
            'author_association': 'NONE',
            'base': {
                'repo': {
                    'html_url': 'https://github.com/ros/rosdistro',
                    'full_name': 'ros/rosdistro',
                },
            },
        },
    }
    with event_path.open('w') as f:
        json.dump(event_data, f)
    with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event_path)}):
        yield event_path


@pytest.fixture(autouse=True)
def mock_github_collaborator_permission_api():
    def _repo_callback(request):
        return (200, {}, json.dumps({
            'name': 'repo',
            'url': request.url.replace(':443', ''),
        }))

    def _permission_callback(request):
        if 'existing_golf' in request.url:
            return (200, {}, json.dumps({'permission': 'read'}))
        if 'existing_hotel' in request.url:
            return (500, {}, json.dumps({'message': 'Internal Server Error'}))
        return (200, {}, json.dumps({'permission': 'admin'}))

    with responses.RequestsMock(
        assert_all_requests_are_fired=False
    ) as mock_responses:
        mock_responses.add_callback(
            responses.GET,
            re.compile(
                r'https://api\.github\.com(:443)?/repos/[^/]+/[^/]+$'),
            callback=_repo_callback,
            content_type='application/json',
        )
        mock_responses.add_callback(
            responses.GET,
            re.compile(
                r'https://api\.github\.com(:443)?/repos/[^/]+/[^/]+'
                r'/collaborators/[^/]+/permission'),
            callback=_permission_callback,
            content_type='application/json',
        )
        yield mock_responses


@pytest.fixture
def rosdistro_index_repo(empty_repo) -> Iterable[Repo]:
    repo_dir = Path(empty_repo.working_tree_dir)

    index_path = _write_distributions(EXISTING_DISTROS, repo_dir)

    for distro_name in EXISTING_DISTROS.keys():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        empty_repo.index.add(str(file_path))

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
        return second


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
        'invalid__name_existing': {
            'source': {
                'type': 'git',
                'url': 'https://example.com/invalid__name_existing.git',
                'version': 'main',
            },
        },
    },
    'jazzy': {
        'existing_golf': {
            'release': {
                'url':
                    'https://github.com/ros2-gbp/existing_golf-release.git',
                'version': '1.0.0-1',
            },
        },
        'existing_jazzy': {
            'release': {
                'url':
                    'https://github.com/ros2-gbp/existing_jazzy-release.git',
                'version': '1.0.0-1',
            },
            'source': {
                'type': 'git',
                'url': 'https://example.com/existing_jazzy.git',
                'version': 'main',
            },
        },
        'non_github_release': {
            'release': {
                'url': 'https://example.com/non_github_release.git',
                'version': '1.0.0-1',
            },
        },
        'existing_hotel': {
            'release': {
                'url':
                    'https://github.com/ros2-gbp/existing_hotel-release.git',
                'version': '1.0.0-1',
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
    'jazzy': {
        'control_charlie': {
            'release': {
                'url':
                    'https://github.com/ros2-gbp/control_charlie-release.git',
                'version': '1.0.0-1',
            },
        },
        'control_delta': {
            'release': {
                'url': 'https://github.com/other/control_delta-release.git',
                'version': '1.0.0-1',
            },
        },
    },
}


# This is a list of circumstances which require further review.
SENSITIVE = {
    '*': CONTROL_DISTROS,
    'A': {
        # This release stanza is not hosted on GitHub
        'jazzy': {
            'non_github_release': {
                'release': {
                    'version': '1.0.0-2',
                },
            },
        },
    },
    'B': {
        # This release URL was modified
        'jazzy': {
            'existing_jazzy': {
                'release': {
                    'url':
                        'https://github.com/other/modified_jazzy-release.git',
                },
            },
        },
    },
    'C': {
        # Collaborator permissions could not be queried
        'jazzy': {
            'existing_hotel': {
                'release': {
                    'version': '1.0.0-2',
                },
            },
        },
    },
}


# This is a list of violations to check for.
# To avoid collisions, each check should use unique repo names.
VIOLATIONS = {
    '*': _merge_all_distros(SENSITIVE.values()),
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
                    'packages': ['duplicate_name', 'delta'],
                },
            },
        },
    },
    'C': {
        # This repo has explicit packages that violate REP 144
        'rolling': {
            'foxtrot': {
                'release': {
                    'packages': [
                        'invalid__name', '1invalid', 'i', 'A_invalid'
                    ],
                },
            },
        },
    },
    'D': {
        # This repo has an implicit package name that violates REP 144
        'rolling': {
            'invalid__repo_name': {
                'release': {
                    'url': 'https://example.com/invalid__repo_name.git',
                    'version': '1.0.0-1',
                },
            },
        },
    },
    'E': {
        # This rolling repo has a release URL outside of ros2-gbp
        'rolling': {
            'wrong_org': {
                'release': {
                    'url': 'https://github.com/other/wrong_org-release.git',
                    'version': '1.0.0-1',
                },
            },
        },
    },
    'F': {
        # This modifies release stanzas in multiple distros
        'rolling': {
            'control_bravo_release': {
                'release': {
                    'version': '1.0.0-1',
                },
            },
        },
        'jazzy': {
            'control_delta_release': {
                'release': {
                    'version': '1.0.0-1',
                },
            },
        },
    },
    'G': {
        # The submitting user is not authorized to modify this repository
        'jazzy': {
            'existing_golf': {
                'release': {
                    'version': '1.0.0-2',
                },
            },
        },
    },
}


def pytest_generate_tests(metafunc):
    if 'violation_distros' in metafunc.fixturenames:
        combinations = {
            ''.join(key_set): _merge_all_distros(map(VIOLATIONS.get, key_set))
            for key_set in _all_combinations(sorted(VIOLATIONS.keys()))
            if key_set != ('*',)
        }
        metafunc.parametrize(
            'violation_distros',
            combinations.values(),
            ids=combinations.keys())
    if 'sensitive_distros' in metafunc.fixturenames:
        combinations = {
            ''.join(key_set): _merge_all_distros(map(SENSITIVE.get, key_set))
            for key_set in _all_combinations(sorted(SENSITIVE.keys()))
            if key_set != ('*',)
        }
        metafunc.parametrize(
            'sensitive_distros',
            combinations.values(),
            ids=combinations.keys())


@pytest.mark.usefixtures('mock_github_event')
def test_control(rosdistro_index_repo):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    distros = _merge_distributions(EXISTING_DISTROS, CONTROL_DISTROS)
    _write_distributions(distros, repo_dir)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria is not None and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)


def test_target_ref(rosdistro_index_repo):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    distros = _merge_distributions(EXISTING_DISTROS, CONTROL_DISTROS)
    index_path = _write_distributions(distros, repo_dir)

    for distro_name in distros.keys():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        rosdistro_index_repo.index.add(str(file_path))
    rosdistro_index_repo.index.add(str(index_path))
    rosdistro_index_repo.index.commit('Add control distros')

    violation_distros = VIOLATIONS['E']
    violation_merged = _merge_distributions(distros, violation_distros)
    _write_distributions(violation_merged, repo_dir)

    criteria, annotations = extension.analyze(repo_dir, head_ref='HEAD')
    assert criteria and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)

    for distro_name in violation_merged.keys():
        file_path = repo_dir / distro_name / 'distribution.yaml'
        rosdistro_index_repo.index.add(str(file_path))
    rosdistro_index_repo.index.add(str(index_path))
    rosdistro_index_repo.index.commit('Add check violation')

    criteria, annotations = extension.analyze(repo_dir, head_ref='HEAD')
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)


def test_removal_only(rosdistro_index_repo):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    _write_distributions({distro: {} for distro in EXISTING_DISTROS}, repo_dir)

    assert (None, None) == extension.analyze(repo_dir)


@pytest.mark.usefixtures('mock_github_non_member_event')
def test_sensitive(rosdistro_index_repo, sensitive_distros):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    distros = _merge_distributions(EXISTING_DISTROS, sensitive_distros)
    _write_distributions(distros, repo_dir)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE > c.recommendation for c in criteria)


@pytest.mark.usefixtures('mock_github_non_member_event')
def test_violation(rosdistro_index_repo, violation_distros):
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    distros = _merge_distributions(EXISTING_DISTROS, violation_distros)
    _write_distributions(distros, repo_dir)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)

    # Verify that all annotation lines were actually changed
    distro_files = [
        str(Path(distro_name) / 'distribution.yaml')
        for distro_name in distros.keys()
    ]
    changed_yaml = get_changed_yaml(repo_dir, distro_files)
    added_lines = get_added_lines(repo_dir) if changed_yaml else None
    for annotation in annotations:
        file_added = (added_lines or {}).get(annotation.file, ())
        assert file_added, f'No changed lines found for {annotation.file}'
        assert all(
            any(line in r for r in file_added)
            for line in annotation.lines
        ), f'Annotation {annotation} references lines not in changed lines'


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
    _write_distributions(merged_distros, repo_dir)

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


@pytest.fixture
def repo_with_syntax_error_index(rosdistro_index_repo: Repo) -> Repo:
    assert rosdistro_index_repo.working_tree_dir is not None
    repo_dir = Path(rosdistro_index_repo.working_tree_dir)
    index_path = repo_dir / 'index-v4.yaml'
    index_path.write_text('---\nfoo: @bar\n')
    return rosdistro_index_repo


def test_rosdistro_syntax_error_on_disk(
    repo_with_syntax_error_index: Repo,
) -> None:
    assert repo_with_syntax_error_index.working_tree_dir is not None
    repo_dir = Path(repo_with_syntax_error_index.working_tree_dir)
    extension = RosdistroAnalyzer()

    with pytest.raises(yaml.MarkedYAMLError) as e:
        extension.analyze(repo_dir)

    assert e.value.problem_mark is not None
    assert e.value.problem_mark.name == 'index-v4.yaml'
    assert e.value.problem_mark.line == 1


def test_rosdistro_syntax_error_in_git_ref(
    repo_with_syntax_error_index: Repo,
) -> None:
    assert repo_with_syntax_error_index.working_tree_dir is not None
    repo_dir = Path(repo_with_syntax_error_index.working_tree_dir)
    extension = RosdistroAnalyzer()

    index_path = repo_dir / 'index-v4.yaml'
    repo_with_syntax_error_index.index.add(str(index_path))
    repo_with_syntax_error_index.index.commit('Commit invalid index')

    with pytest.raises(yaml.MarkedYAMLError) as e:
        extension.analyze(repo_dir, target_ref='HEAD~1', head_ref='HEAD')

    assert e.value.problem_mark is not None
    assert e.value.problem_mark.name == 'index-v4.yaml'
    assert e.value.problem_mark.line == 1


def _write_with_header(repo_dir, header, version):
    file_path = repo_dir / 'humble' / 'distribution.yaml'
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        header + 'repositories:\n  foo:\n    release:\n'
        f'      url: https://github.com/ros2-gbp/foo-release.git\n'
        f'      version: {version}\n')
    index_path = repo_dir / 'index-v4.yaml'
    index_path.write_text(yaml.dump(_generate_index(['humble'])))
    return file_path, index_path


@pytest.mark.usefixtures('mock_github_event')
@pytest.mark.parametrize('with_release_change', (False, True))
def test_distribution_header_modified(empty_repo, with_release_change):
    repo_dir = Path(empty_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    old_header = (
        '%YAML 1.1\n# see REP 143: https://reps.openrobotics.org/rep-0143/\n'
        '---\n')
    new_header = (
        '%YAML 1.1\n# see REP 143: http://ros.org/reps/rep-0143.html\n'
        '---\n')

    file_path, index_path = _write_with_header(repo_dir, old_header, '1.0.0-1')
    empty_repo.index.add([str(file_path), str(index_path)])
    empty_repo.index.commit('Add distribution')

    _write_with_header(
        repo_dir, new_header, '1.0.1-1' if with_release_change else '1.0.0-1')

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria
    assert any(
        Recommendation.DISAPPROVE == c.recommendation and
        'headers' in c.rationale for c in criteria)
    assert any(
        Path(a.file) == Path('humble/distribution.yaml') and
        a.lines == range(2, 3)
        for a in annotations)


@pytest.mark.usefixtures('mock_github_event')
def test_distribution_header_unmodified(empty_repo):
    repo_dir = Path(empty_repo.working_tree_dir)
    extension = RosdistroAnalyzer()

    header = '%YAML 1.1\n# ROS distribution file\n---\n'
    file_path, index_path = _write_with_header(repo_dir, header, '1.0.0-1')
    empty_repo.index.add([str(file_path), str(index_path)])
    empty_repo.index.commit('Add distribution')

    _write_with_header(repo_dir, header, '1.0.1-1')

    criteria, _ = extension.analyze(repo_dir)
    assert criteria
    assert not any('headers' in c.rationale for c in criteria)
