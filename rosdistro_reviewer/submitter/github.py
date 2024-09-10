# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import logging
import os

from colcon_core.environment_variable import EnvironmentVariable
from colcon_core.logging import colcon_logger
from colcon_core.logging import get_effective_console_level
from colcon_core.plugin_system import satisfies_version
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Recommendation
from rosdistro_reviewer.submitter import ReviewSubmitterExtensionPoint

"""Environment variable for the GitHub authentication token"""
GITHUB_TOKEN_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'GITHUB_TOKEN', 'Authentication token secret for GitHub')


class GitHubSubmitter(ReviewSubmitterExtensionPoint):
    """Submit reviews to GitHub pull requests."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ReviewSubmitterExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser) -> None:  # noqa: D102
        parser.add_argument('--github-pull-request', required=False,
                            metavar='GH_ORG/GH_REPO#PR_ID',
                            help='GitHub pull request to submit this code '
                                 'review to')

    def submit(self, args, review) -> None:  # noqa: D102
        from github import Auth
        from github import Github
        from github.PullRequest import ReviewComment

        log_level = get_effective_console_level(colcon_logger)
        logging.getLogger('urllib3.connectionpool').setLevel(log_level)

        pull_request = getattr(args, 'github_pull_request', None)
        if pull_request is None:
            return None

        try:
            repo_id, pr_id_str = pull_request.rsplit('#', 1)
            pr_id = int(pr_id_str)
        except ValueError as exc:
            raise ValueError('Invalid pull request reference') from exc

        token = os.environ.get(GITHUB_TOKEN_ENVIRONMENT_VARIABLE.name)
        auth = Auth.Token(token) if token else None

        RECOMMENDATION_EVENTS = {
            Recommendation.DISAPPROVE: 'REQUEST_CHANGES',
            Recommendation.NEUTRAL: 'COMMENT',
            Recommendation.APPROVE: 'APPROVE',
        }

        def _annotation_to_comment(
            annotation: Annotation,
        ) -> ReviewComment:
            if annotation.lines.stop == annotation.lines.start + 1:
                return ReviewComment(
                    path=annotation.file,
                    body=annotation.message,
                    line=annotation.lines.start,
                    side='RIGHT')
            else:
                return ReviewComment(
                    path=annotation.file,
                    body=annotation.message,
                    line=annotation.lines.stop - 1,
                    side='RIGHT',
                    start_line=annotation.lines.start,
                    start_side='RIGHT')

        comments = list(map(_annotation_to_comment, review.annotations))

        github = Github(auth=auth) if auth else Github()
        repo = github.get_repo(repo_id)
        pr = repo.get_pull(pr_id)

        message = review.summarize()
        recommendation = review.recommendation

        pr.create_review(
            body=message,
            event=RECOMMENDATION_EVENTS[recommendation],
            comments=comments)