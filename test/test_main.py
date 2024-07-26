# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from runpy import run_module
from unittest.mock import patch

import pytest


@patch(
    'colcon_core.argument_parser.get_argument_parser_extensions',
    return_value={},
)
def test_main(get_argument_parser_extensions):
    with patch('sys.argv', ['__main__', '--help']):
        with pytest.raises(SystemExit) as e:
            run_module('rosdistro_reviewer')
    assert e.value.code == 0

    with patch(
        'rosdistro_reviewer.verb.review.ReviewVerb.main',
        return_value=42,
    ) as verb_main:
        with patch('sys.argv', ['__main__', '--log-base', '/dev/null']):
            with pytest.raises(SystemExit) as e:
                run_module('rosdistro_reviewer')
        assert e.value.code == 42
        verb_main.assert_called_once()
