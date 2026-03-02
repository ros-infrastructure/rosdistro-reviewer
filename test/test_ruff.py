# Copyright 2018 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
import subprocess
import sys

import pytest


@pytest.mark.linter
@pytest.mark.ruff
def test_ruff_check() -> None:
    result = subprocess.run(
        [sys.executable, '-m', 'ruff', 'check', '.'],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        check=False,
    )
    assert 0 == result.returncode, 'ruff check found violations'
