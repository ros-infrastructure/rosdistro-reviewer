# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
from typing import Iterable

from git import Repo
import pytest


# Configure tests to use the 'files' backend by default, regardless of
# the global git configuration. Older git versions do not support the
# '--ref-format' argument to 'git init', but they will ignore this
# configuration parameter, ensuring backward compatibility.
os.environ['GIT_CONFIG_PARAMETERS'] = (
    os.environ.get('GIT_CONFIG_PARAMETERS', '') +
    " 'init.defaultRefFormat=files'"
).strip()


@pytest.fixture
def empty_repo(tmp_path_factory) -> Iterable[Repo]:
    tmp_path = tmp_path_factory.mktemp('repo')
    with Repo.init(tmp_path) as repo:
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
