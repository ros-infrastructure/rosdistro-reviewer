# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import traceback
from typing import Dict
from typing import Optional

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import instantiate_extensions

logger = colcon_logger.getChild(__name__)


class ReviewSubmitterExtensionPoint:
    """The interface for submitting code reviews."""

    """The version of the element analyzer extension interface."""
    EXTENSION_POINT_VERSION = '1.0'

    def add_arguments(self, *, parser) -> None:
        """
        Add command line arguments specific to the review submission.

        The method is intended to be overridden in a subclass.

        :param parser: The argument parser
        """
        pass

    def submit(self, args, review) -> None:
        """
        Submit a code review.

        The method is intended to be overridden in a subclass.

        :param args: The parsed command line arguments
        :param review: The code review to submit
        """
        raise NotImplementedError()


def get_review_submitter_extensions(
    *,
    group_name: Optional[str] = None,
) -> Dict[str, ReviewSubmitterExtensionPoint]:
    """
    Get the available review submitter extensions.

    :param group_name: Optional extension point group name override
    :rtype: Dict
    """
    if group_name is None:
        group_name = __name__
    return instantiate_extensions(group_name)


def add_review_submitter_arguments(parser, *, extensions=None) -> None:
    """
    Add the command line arguments for the review submitter extensions.

    :param parser: The argument parser
    :param extensions: The review submitter extensions to use, if `None` is
      passed use the extensions provided by
      :function:`get_review_submitter_extensions`
    """
    if extensions is None:
        extensions = get_review_submitter_extensions()
    group = parser.add_argument_group(title='Review submission arguments')
    for extension in extensions.values():
        extension.add_arguments(parser=group)


def submit_review(args, review, *, extensions=None) -> None:
    """
    Submit a code review to all enabled submitter extensions.

    :param args: The parsed command line arguments
    :param review: The code review to submit
    :param extensions: The review submitter extensions to use, if `None` is
      passed use the extensions provided by
      :function:`get_review_submitter_extensions`
    """
    if extensions is None:
        extensions = get_review_submitter_extensions()
    for submitter_name, extension in extensions.items():
        try:
            extension.submit(args, review)
        except Exception as e:  # noqa: F841
            exc = traceback.format_exc()
            logger.error(
                'Exception in review submitter extension '
                f"'{submitter_name}': {e}\n{exc}")
