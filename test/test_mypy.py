# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
import subprocess
import sys

import pytest


def _have_compatible_github():
    """
    Determine if a compatible version of PyGithub is available.

    Of note, PyGithub doesn't expose a __version__ attribute. We could try to
    figure it out by performing package discovery, but we probably couldn't
    parse and compare the version numbers without taking a new dependency,
    which feels like a lot of work just to avoid running mypy on older
    platforms...
    """
    try:
        from github import Auth  # noqa: F401
        from github import Github  # noqa: F401
        from github.PullRequest import ReviewComment  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.linter
def test_mypy() -> None:
    exclude = []
    if not _have_compatible_github():
        exclude.append(r'/submitter/github\.py$')

    result = subprocess.run(
        [
            sys.executable, '-m', 'mypy',
            '--namespace-packages', '--explicit-package-bases', '.',
        ] + [
            arg
            for pattern in exclude
            for arg in ('--exclude', pattern)
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        check=False,
    )
    assert 0 == result.returncode, 'mypy found violations'
