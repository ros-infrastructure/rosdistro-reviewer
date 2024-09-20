# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from typing import Iterable

from git import Repo
import pytest


@pytest.fixture
def empty_repo(tmp_path) -> Iterable[Repo]:
    with Repo.init(tmp_path) as repo:
        repo.index.commit('Initial commit')

        base = repo.create_head('main')
        base.checkout()

        yield repo
