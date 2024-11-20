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

INTRODUCTION = """Thanks for sending a pull request to ROS distro!

This is an automated tool that helps check your pull request for correctness.
This tool checks a number of attributes associated with your ROS package and generates a report that helps our reviewers merge your pull request in a timely fashion. Here are a few things to consider when sending adding or updating a package to ROS Distro.
ROS Distro includes a very helpful [CONTRIBUTING.md](https://github.com/ros/rosdistro/blob/master/CONTRIBUTING.md) file that we recommend reading if it is your first time submitting a package.
Please also read the [ROS Distro review guidelines](https://github.com/rosdistro/rosdistro/blob/master/REVIEW_GUIDELINES.md) which summarizes this release process.

# ROS Distro Considerations
* ROS Distributions are created using [REP-134 Standards Track](https://ros.org/reps/rep-0143.html) as a guide.
* Your package name should comply to [REP-144 ROS Package Naming](https://www.ros.org/reps/rep-0144.html)
* Your package must build for all platforms and architectures on the ROS buildfarm. See [REP-2000 ROS Releases and Supported Platforms](https://www.ros.org/reps/rep-2000.html) for all supported platforms for your ROS Distro.
* Your package must contain an [OSI approved license](https://opensource.org/licenses). Your `package.xml` file must also include that license in a machine readable format. See [REP-149 Package Manifest Format Three Specification](https://ros.org/reps/rep-0149.html#license-multiple-but-at-least-one) for additional details.
* A publicly available, open source, repository for your ROS package.
* While not required, we recommend that you create an account for ROS Discourse and subscribe to the [appropriate release topic](https://discourse.ros.org/c/release/16).
* If you would like, you may join our [Discord Server](https://discord.com/servers/open-robotics-1077825543698927656) and ask questions in the `#infra-help` channel.

# Package Considerations

Having your package included in a ROS Distro is a badge of quality, and we recommend that package developers strive to create packages of the highest quality. We recommend package developers review the following resources before submitting their package.

* [REP-2004 Package Quality Declaration](https://www.ros.org/reps/rep-2004.html)-- The ROS 2 TSC has created a quality rating system for ROS packages. These ratings should serve as a guide for package developers. We recommend package developers achieve a quality level of three or higher.
* Documentation -- it is recommended that ROS packages include an extensive [README.md file, and API level documentation using the Sphinx documentation system](https://docs.ros.org/en/rolling/How-To-Guides/Documenting-a-ROS-2-Package.html).
* Maintainer Responsibilities -- the ROS 2 documentation includes a guide to [ROS package maintainer responsibilities](https://docs.ros.org/en/rolling/How-To-Guides/Core-maintainer-guide.html) that summarizes your responsibilities as an open source maintainer. While we do not enforce these requirements on package maintainers they should be considered best practices.
* We recommend that your package should strive to conform to the [ROS 2 Developer Guide](https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Developer-Guide.html) and the [ROS 2 Style Guide](https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Code-Style-Language-Versions.html).

# Need Help?

Please post your questions to [Robotics Stack Exchange](https://docs.ros.org/) or refer to the `#infra-help` channel on our [Discord server](https://discord.com/servers/open-robotics-1077825543698927656).

---

"""  # noqa: E501


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

        # Check if we've already posted a review for this PR
        already_reviewed = any(
            review.user.login == 'github-actions[bot]'
            for review in pr.get_reviews())
        if not already_reviewed:
            message = INTRODUCTION + message

        pr.create_review(
            body=message,
            event=RECOMMENDATION_EVENTS[recommendation],
            comments=comments)
