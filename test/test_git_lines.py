# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from git import Head
from git import Repo
import pytest
from rosdistro_reviewer.git_lines import get_added_lines


@pytest.fixture(scope='session')
def git_repo(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> Repo:
    repo_dir = tmp_path_factory.mktemp('git_repo')
    repo = Repo.init(repo_dir)
    request.addfinalizer(repo.close)

    repo.index.commit('Initial commit')

    base = repo.create_head('base')
    base.checkout()
    lines_txt = repo_dir / 'lines.txt'
    with open(lines_txt, 'w') as f:
        f.write('\n'.join(['a', 'b', 'c', 'd', 'e', 'B', 'E', '']))
    repo.index.add((str(lines_txt),))
    repo.index.commit('Add lines.txt')

    repo.head.reference = Head(repo, 'refs/heads/orphan')  # type: ignore
    repo.index.commit('Orphaned commit')

    repo.create_head('lines2', 'base').checkout()
    lines2_txt = repo_dir / 'lines2.txt'
    with lines2_txt.open('w') as f:
        f.write('\n'.join(['1', '2']))
    repo.index.add((str(lines2_txt),))
    repo.index.remove(str(lines_txt), working_tree=True)
    repo.index.commit('Add lines2.txt, remove lines.txt')

    repo.create_head('less_c', 'base').checkout()
    with lines_txt.open('w') as f:
        f.write('\n'.join(['a', 'b', 'd', 'e', 'B', 'C', 'E', '']))
    repo.index.add((str(lines_txt),))
    repo.index.commit("Remove 'c' from lines.txt")

    repo.create_head('less_c_d', 'less_c').checkout()
    with lines_txt.open('w') as f:
        f.write('\n'.join(['a', 'b', 'e', 'B', 'C', 'D', 'E', '']))
    repo.index.add((str(lines_txt),))
    repo.index.commit("Remove 'd' from lines.txt")

    repo.create_head('less_a', 'base').checkout()
    with lines_txt.open('w') as f:
        f.write('\n'.join(['b', 'c', 'd', 'e', 'A', 'B', 'E', '']))
    repo.index.add((str(lines_txt),))
    repo.index.commit("Remove 'a' from lines.txt")

    target = repo.create_head('merge_c_d_to_a', 'less_a').checkout()
    other = repo.heads['less_c_d']
    repo.index.merge_tree(other.commit)
    with lines_txt.open('w') as f:
        f.write('\n'.join(['b', 'e', 'A', 'B', 'C', 'D', 'E', '']))
    repo.index.add((str(lines_txt),))
    repo.index.commit(
        "Merge branch 'less_c_d' into merge_c_d_to_a",
        parent_commits=[target.commit, other.commit])  # type: ignore

    with lines_txt.open('a') as f:
        f.write('X\n')

    return repo


def test_added_lines(git_repo: Repo) -> None:
    # Check uncommitted
    lines = get_added_lines(git_repo.working_dir)
    assert lines == {'lines.txt': [range(8, 9)]}

    # Check path targeting
    lines = get_added_lines(git_repo.working_dir, paths=['lines.txt'])
    assert lines == {'lines.txt': [range(8, 9)]}

    # Check path targeting with no match
    lines = get_added_lines(git_repo.working_dir, paths=['foo.txt'])
    assert lines is None

    # Check explicit head
    lines = get_added_lines(git_repo.working_dir, head_ref='less_a')
    assert lines == {'lines.txt': [range(5, 6)]}

    # Check explicit target with no head (including uncommitted)
    lines = get_added_lines(git_repo.working_dir, target_ref='less_c')
    assert lines == {'lines.txt': [range(3, 4), range(6, 7), range(8, 9)]}

    # Check explicit head and target
    lines = get_added_lines(git_repo.working_dir, target_ref='less_c',
                            head_ref='less_c_d')
    assert lines == {'lines.txt': [range(6, 7)]}

    # Check explicit head and target with multiple commits
    lines = get_added_lines(git_repo.working_dir, target_ref='base',
                            head_ref='less_c_d')
    assert lines == {'lines.txt': [range(5, 7)]}

    # Check merge base behavior
    lines = get_added_lines(git_repo.working_dir, target_ref='less_a',
                            head_ref='less_c_d')
    assert lines == {'lines.txt': [range(5, 7)]}

    # Check file being added
    lines = get_added_lines(git_repo.working_dir, target_ref='base',
                            head_ref='lines2')
    assert lines == {'lines2.txt': [range(1, 3)]}

    # Check failure to find merge base
    with pytest.raises(RuntimeError):
        get_added_lines(git_repo.working_dir, target_ref='orphan',
                        head_ref='less_a')
