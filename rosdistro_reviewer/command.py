# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
from typing import Any

from colcon_core.command \
    import LOG_LEVEL_ENVIRONMENT_VARIABLE \
    as COLCON_LOG_LEVEL_ENVIRONMENT_VARIABLE
from colcon_core.command import main as colcon_main
from colcon_core.environment_variable import EnvironmentVariable
from rosdistro_reviewer.verb.review import ReviewVerb

"""Environment variable to set the log level"""
LOG_LEVEL_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'ROSDISTRO_REVIEWER_LOG_LEVEL',
    COLCON_LOG_LEVEL_ENVIRONMENT_VARIABLE.description)

"""Environment variable to set the configuration directory"""
HOME_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'ROSDISTRO_REVIEWER_HOME',
    'Set the configuration directory (default: ~/.rosdistro_reviewer)')


def main(*args: str, **kwargs: str) -> Any:
    """Execute the main logic of the command."""
    colcon_kwargs = {
        'command_name': 'rosdistro-reviewer',
        'verb_group_name': 'rosdistro_reviewer.verb',
        'environment_variable_group_name':
            'rosdistro_reviewer.environment_variable',
        'default_verb': ReviewVerb,
        'default_log_base': os.devnull,
        **kwargs,
    }
    return colcon_main(*args, **colcon_kwargs)
