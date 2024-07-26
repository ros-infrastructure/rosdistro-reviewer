# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import logging
from pathlib import Path

from colcon_core.logging import colcon_logger
from colcon_core.logging import get_effective_console_level
from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint
from rosdistro_reviewer.element_analyzer import analyze
from rosdistro_reviewer.submitter import add_review_submitter_arguments
from rosdistro_reviewer.submitter import submit_review


class ReviewVerb(VerbExtensionPoint):
    """Generate a review for rosdistro changes."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        log_level = get_effective_console_level(colcon_logger)
        logging.getLogger('git').setLevel(log_level)

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--target-ref', default=None, metavar='COMMITTISH',
            help='Git commit-ish to use as the base for determining what '
                 'changes should be reviewed (default: commit prior to '
                 '--head-ref)')
        parser.add_argument(
            '--head-ref', default=None, metavar='COMMITTISH',
            help='Git commit-ish which contains changes that should be '
                 'reviewed (default: uncommitted changes)')

        add_review_submitter_arguments(parser)

    def main(self, *, context):  # noqa: D102
        review = analyze(
            Path.cwd(),
            target_ref=context.args.target_ref,
            head_ref=context.args.head_ref)
        if review:
            root = Path.cwd() if context.args.head_ref is None else None
            print('\n' + review.to_text(root=root) + '\n')

            submit_review(context.args, review)
        return 0
