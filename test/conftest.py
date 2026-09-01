# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from typing import Iterable

from git import Repo
import pytest


@pytest.fixture
def empty_repo(tmp_path_factory) -> Iterable[Repo]:
    tmp_path = tmp_path_factory.mktemp('repo')
    with Repo.init(tmp_path, ref_format='files') as repo:
        repo.index.commit('Initial commit')

        base = repo.create_head('main')
        base.checkout()

        yield repo


@pytest.fixture
def empty_repo_reftable(tmp_path_factory) -> Iterable[Repo]:
    from git import GitCommandError
    tmp_path = tmp_path_factory.mktemp('repo_reftable')
    try:
        repo = Repo.init(tmp_path, ref_format='reftable')
    except GitCommandError:
        pytest.skip(
            'reftable ref format is not supported by local git version')

    with repo:
        yield repo
