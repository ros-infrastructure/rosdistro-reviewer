# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import itertools
from pathlib import Path
from typing import Iterable

from git import Repo
import pytest
from rosdistro_reviewer.element_analyzer.rosdep import RosdepAnalyzer
from rosdistro_reviewer.review import Recommendation
import yaml


@pytest.fixture
def rosdep_repo(empty_repo) -> Iterable[Repo]:
    repo_dir = Path(empty_repo.working_tree_dir)
    (repo_dir / 'rosdep').mkdir()

    for file_name, data in EXISTING_RULES.items():
        file_path = repo_dir / 'rosdep' / file_name
        with file_path.open('w') as f:
            yaml.dump(data, f)

        empty_repo.index.add(str(file_path))

    empty_repo.index.commit('Add rosdep files')

    return empty_repo


def test_no_files(empty_repo):
    repo_dir = Path(empty_repo.working_tree_dir)
    extension = RosdepAnalyzer()
    assert (None, None) == extension.analyze(repo_dir)


def test_no_changes(rosdep_repo):
    repo_dir = Path(rosdep_repo.working_tree_dir)
    extension = RosdepAnalyzer()
    assert (None, None) == extension.analyze(repo_dir)


def _all_combinations(iterable):
    for r in range(1, 3):
        yield from itertools.combinations(iterable, r)


def _merge_two_rules(first, second):
    if isinstance(first, dict):
        assert isinstance(second, dict)
        result = dict(first)
        for k, v in second.items():
            if k not in result:
                result[k] = v
            else:
                result[k] = _merge_two_rules(result[k], v)
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
                result.append(_merge_two_rules(v, second[i]))
        for v in second:
            if v not in result:
                result.append(v)
        return result
    else:
        assert first == second
        return first


def _merge_all_rules(rules_list):
    result = {}
    for rules in rules_list:
        result = _merge_two_rules(result, rules)
    return result


# These rules are already committed to the db and aren't part of the change.
# They must be syntactically correct, but do not necessarily need to pass
# the checks.
EXISTING_RULES = {
    'base.yaml': {
        'existing-golf': {
            'fedora': ['existing-golf'],
        },
        'existing-hotel': {
            'ubuntu': {
                '*': {
                    'apt': {
                        'packages': ['existing-hotel'],
                    },
                },
            },
        },
    },
    'python.yaml': {
        'python.yaml': {
            'python3-existing-india': {
                'fedora': ['python3-existing-india'],
            },
        },
    },
}


# These are the "control" rules for rosdep check validation.
# Each one must pass all checks and be syntactically correct.
CONTROL_RULES = {
    'base.yaml': {
        'control-alpha': {
            'debian': {
                'apt': {
                    'packages': ['control-alpha'],
                },
            },
            'ubuntu': {
                '*': {
                    'apt': {
                        'packages': ['control-alpha'],
                    },
                },
            },
        },
    },
    'python.yaml': {
        'python3-control-bravo': {
            '*': {
                'pip': {
                    'packages': ['python3-control-bravo'],
                },
            },
            'ubuntu': ['python3-control-bravo'],
        },
        'python3-control-bravo-pip': {
            '*': {
                'pip': {
                    'packages': ['python3-control-bravo'],
                },
            },
        },
        'python3-control-charlie': {
            'fedora': ['python3-control-charlie'],
            'ubuntu': None,
        },
    },
}


# This is a list of violations to check for.
# To avoid collisions, each check should use unique package names.
VIOLATIONS = {
    '*': CONTROL_RULES,
    'A': {
        # This key should end in -pip
        'python.yaml': {
            'python3-alpha': {
                '*': {
                    'pip': {
                        'packages': ['alpha'],
                    },
                },
            },
        },
    },
    'B': {
        # This key should not end in -pip
        'python.yaml': {
            'python3-bravo-pip': {
                'fedora': ['python3-bravo'],
            },
        },
    },
    'C': {
        # This key belongs in python.yaml
        'base.yaml': {
            'python3-charlie': {
                'ubuntu': ['python3-charlie'],
            },
        },
    },
    'D': {
        # This key name should match the ubuntu package name
        'base.yaml': {
            'delta': {
                'ubuntu': ['libdelta'],
            },
        },
    },
    'E': {
        # This key name should match the ubuntu package name
        'base.yaml': {
            'echo': {
                'ubuntu': {
                    '*': {
                        'apt': {
                            'packages': ['libdelta'],
                        },
                    },
                },
            },
        },
    },
    'F': {
        # This key is defined in multiple files
        'base.yaml': {
            'foxtrot': {
                'ubuntu': ['foxtrot'],
            },
        },
        'python.yaml': {
            'foxtrot': {
                '*': {
                    'pip': {
                        'packages': ['foxtrot'],
                    },
                },
            },
        },
    },
    'G': {
        # This is a rule for an unsupported OS
        'base.yaml': {
            'existing-golf': {
                'archlinux': ['golf'],
            },
        },
    },
    'H': {
        # This is a rule for an unsupported version of Ubuntu
        'base.yaml': {
            'existing-hotel': {
                'ubuntu': {
                    'xenial': ['hotel'],
                },
            },
        },
    },
    'I': {
        # The pip installer is not supported on Gentoo
        'python.yaml': {
            'python3-existing-india': {
                'gentoo': {
                    'pip': {
                        'packages': ['india'],
                    },
                },
            },
        },
    },
    'J': {
        # The pip installer is not supported on Gentoo
        'python.yaml': {
            'python3-juliet-pip': {
                'gentoo': {
                    '*': {
                        'pip': {
                            'packages': ['juliet'],
                        },
                    },
                },
            },
        },
    },
}


def pytest_generate_tests(metafunc):
    if 'violation_rules' not in metafunc.fixturenames:
        return
    combinations = {
        ''.join(key_set): _merge_all_rules(map(VIOLATIONS.get, key_set))
        for key_set in _all_combinations(sorted(VIOLATIONS.keys()))
        if key_set != ('*',)
    }
    metafunc.parametrize(
        'violation_rules',
        combinations.values(),
        ids=combinations.keys())


def test_control(rosdep_repo):
    repo_dir = Path(rosdep_repo.working_tree_dir)
    extension = RosdepAnalyzer()

    rules = _merge_two_rules(EXISTING_RULES, CONTROL_RULES)
    for file_name, data in rules.items():
        file_path = repo_dir / 'rosdep' / file_name
        with file_path.open('w') as f:
            yaml.dump(data, f)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)


def test_target_ref(rosdep_repo):
    repo_dir = Path(rosdep_repo.working_tree_dir)
    extension = RosdepAnalyzer()

    rules = _merge_two_rules(EXISTING_RULES, CONTROL_RULES)
    for file_name, data in rules.items():
        file_path = repo_dir / 'rosdep' / file_name
        with file_path.open('w') as f:
            yaml.dump(data, f)

        rosdep_repo.index.add(str(file_path))

    rosdep_repo.index.commit('Add control rules')

    # Add some violations to the stage, choose set 'A' as candidate
    rules = _merge_two_rules(rules, VIOLATIONS['A'])
    for file_name, data in rules.items():
        file_path = repo_dir / 'rosdep' / file_name
        with file_path.open('w') as f:
            yaml.dump(data, f)

    criteria, annotations = extension.analyze(repo_dir, head_ref='HEAD')
    assert criteria and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)


def test_removal_only(rosdep_repo):
    repo_dir = Path(rosdep_repo.working_tree_dir)
    extension = RosdepAnalyzer()

    for file_name in EXISTING_RULES.keys():
        (repo_dir / 'rosdep' / file_name).write_text('')

    assert (None, None) == extension.analyze(repo_dir)


def test_violation(rosdep_repo, violation_rules):
    repo_dir = Path(rosdep_repo.working_tree_dir)
    extension = RosdepAnalyzer()

    rules = _merge_two_rules(EXISTING_RULES, violation_rules)
    for file_name, data in rules.items():
        file_path = repo_dir / 'rosdep' / file_name
        with file_path.open('w') as f:
            yaml.dump(data, f)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)
