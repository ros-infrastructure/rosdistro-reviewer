# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path

from git import Repo
import pytest
from rosdistro_reviewer.yaml_changes import get_changed_yaml
import yaml


@pytest.fixture
def repo_with_invalid_yaml(empty_repo: Repo) -> Repo:
    assert empty_repo.working_tree_dir
    repo_dir = Path(empty_repo.working_tree_dir)

    subdir = repo_dir / 'subdir'
    subdir.mkdir()

    yaml_file = subdir / 'test.yaml'
    yaml_file.write_text('foo:\n  bar: baz\n')

    empty_repo.index.add(str(yaml_file))
    empty_repo.index.commit('Add test.yaml')

    # Modify it to contain a syntax error.
    yaml_file.write_text('---\nfoo: @bar\n')

    return empty_repo


def test_yaml_syntax_error_on_disk(repo_with_invalid_yaml: Repo) -> None:
    assert repo_with_invalid_yaml.working_tree_dir is not None
    repo_dir = Path(repo_with_invalid_yaml.working_tree_dir)

    yaml_path = 'subdir/test.yaml'

    with pytest.raises(yaml.MarkedYAMLError) as e:
        get_changed_yaml(
            repo_dir,
            [yaml_path],
        )

    assert e.value.problem_mark is not None
    assert e.value.problem_mark.name == str(Path(yaml_path))
    assert e.value.problem_mark.line == 1


def test_yaml_syntax_error_in_git_ref(repo_with_invalid_yaml: Repo) -> None:
    assert repo_with_invalid_yaml.working_tree_dir is not None
    repo_dir = Path(repo_with_invalid_yaml.working_tree_dir)

    yaml_path = 'subdir/test.yaml'
    yaml_file = repo_dir / yaml_path

    repo_with_invalid_yaml.index.add(str(yaml_file))
    repo_with_invalid_yaml.index.commit('Commit invalid yaml')

    with pytest.raises(yaml.MarkedYAMLError) as e:
        get_changed_yaml(
            repo_dir,
            [yaml_path],
            target_ref='HEAD~1',
            head_ref='HEAD',
        )

    assert e.value.problem_mark is not None
    assert e.value.problem_mark.name == str(Path(yaml_path))
    assert e.value.problem_mark.line == 1
