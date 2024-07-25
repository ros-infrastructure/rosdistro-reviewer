# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
import subprocess
import sys

import pytest


@pytest.mark.linter
def test_mypy() -> None:
    result = subprocess.run(
        [
            sys.executable, '-m', 'mypy',
            '--namespace-packages', '--explicit-package-bases', '.',
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        check=False,
    )
    assert 0 == result.returncode, 'mypy found violations'
