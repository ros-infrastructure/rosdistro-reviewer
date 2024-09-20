# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Iterable

from git import Repo
import pytest
from rosdistro_reviewer.element_analyzer.yamllint import YamllintAnalyzer
from rosdistro_reviewer.review import Recommendation

# The control prefix intentionally contains a violation
# to verify that we only surface problems related to new lines
CONTROL_PREFIX = 'alpha: \n  bravo: charlie\n'
CONTROL_SUFFIX = 'yankee:\n  - zulu\n'


@pytest.fixture
def repo_with_yaml(empty_repo) -> Iterable[Repo]:
    repo_dir = Path(empty_repo.working_tree_dir)
    (repo_dir / 'subdir').mkdir()

    yaml_file = repo_dir / 'subdir' / 'file.yaml'
    yaml_file.write_text(CONTROL_PREFIX)

    empty_repo.index.add(str(yaml_file))
    empty_repo.index.commit('Add YAML files')

    return empty_repo


def test_no_files(empty_repo):
    repo_dir = Path(empty_repo.working_tree_dir)
    extension = YamllintAnalyzer()
    assert (None, None) == extension.analyze(repo_dir)


def test_no_changes(repo_with_yaml):
    repo_dir = Path(repo_with_yaml.working_tree_dir)
    extension = YamllintAnalyzer()
    assert (None, None) == extension.analyze(repo_dir)


VIOLATIONS = (
    # Trailing whitespace
    'delta: null ',
    # Not enough indentation
    'echo:\n foxtrot: null',
    # Too much indentation
    'golf:\n   hotel: null',
    # Too many spaces
    'india:  null',
)


def test_control(repo_with_yaml):
    repo_dir = Path(repo_with_yaml.working_tree_dir)
    extension = YamllintAnalyzer()

    (repo_dir / 'subdir' / 'file.yaml').write_text(''.join((
        CONTROL_PREFIX,
        CONTROL_SUFFIX,
    )))

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)


def test_target_ref(repo_with_yaml):
    repo_dir = Path(repo_with_yaml.working_tree_dir)
    extension = YamllintAnalyzer()

    yaml_file = repo_dir / 'subdir' / 'file.yaml'
    yaml_file.write_text(''.join((
        CONTROL_PREFIX,
        CONTROL_SUFFIX,
    )))

    repo_with_yaml.index.add(str(yaml_file))
    repo_with_yaml.index.commit('Add more to the YAML file')

    yaml_file.write_text(''.join((
        CONTROL_PREFIX,
        'problem:  line \n',
        CONTROL_SUFFIX,
    )))

    criteria, annotations = extension.analyze(repo_dir, head_ref='HEAD')
    assert criteria and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)


def test_yamllint_config(repo_with_yaml):
    repo_dir = Path(repo_with_yaml.working_tree_dir)
    extension = YamllintAnalyzer()

    (repo_dir / 'subdir' / 'file.yaml').write_text(''.join((
        CONTROL_PREFIX,
        'delta: null  # comment\n',
        CONTROL_SUFFIX,
    )))

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and not annotations
    assert all(Recommendation.APPROVE == c.recommendation for c in criteria)

    (repo_dir / '.yamllint').write_text('\n'.join((
        'extends: default',
        'rules:',
        '  comments:',
        '    min-spaces-from-content: 4',
    )))

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)


def test_removal_only(repo_with_yaml):
    repo_dir = Path(repo_with_yaml.working_tree_dir)
    extension = YamllintAnalyzer()

    (repo_dir / 'subdir' / 'file.yaml').write_text('')

    assert (None, None) == extension.analyze(repo_dir)


@pytest.mark.parametrize(
    'violation', VIOLATIONS, ids=range(len(VIOLATIONS)))
def test_violation(repo_with_yaml, violation):
    repo_dir = Path(repo_with_yaml.working_tree_dir)
    extension = YamllintAnalyzer()

    (repo_dir / 'subdir' / 'file.yaml').write_text(''.join((
        CONTROL_PREFIX,
        violation + '\n',
        CONTROL_SUFFIX,
    )))

    criteria, annotations = extension.analyze(repo_dir)
    assert criteria and annotations
    assert any(Recommendation.APPROVE != c.recommendation for c in criteria)
