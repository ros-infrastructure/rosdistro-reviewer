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


def _find_repo_root():
    # We delay this import until after the GitPython
    # logger has already been configured to avoid DEBUG
    # messages on the console at import time
    from git import Repo
    from git import InvalidGitRepositoryError
    try:
        with Repo(Path.cwd(), search_parent_directories=True) as repo:
            return Path(repo.working_tree_dir)
    except InvalidGitRepositoryError as e:
        raise RuntimeError(
            'This tool must be run from within a git repository') from e


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
        root = _find_repo_root()
        review = analyze(
            root,
            target_ref=context.args.target_ref,
            head_ref=context.args.head_ref)
        if review:
            text_root = root if context.args.head_ref is None else None
            print('\n' + review.to_text(root=text_root) + '\n')

            submit_review(context.args, review)
        return 0
