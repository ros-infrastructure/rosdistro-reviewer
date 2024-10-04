# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import List
from typing import Optional
from typing import Tuple
from unittest.mock import Mock
from unittest.mock import patch

from colcon_core.command import CommandContext
from colcon_core.plugin_system import satisfies_version
import pytest
from rosdistro_reviewer.element_analyzer import ElementAnalyzerExtensionPoint
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.submitter import ReviewSubmitterExtensionPoint
from rosdistro_reviewer.verb.review import ReviewVerb


class NoopAnalyzer(ElementAnalyzerExtensionPoint):

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ElementAnalyzerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def analyze(  # noqa: D102
        self,
        path: Path,
        target_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
    ) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:
        return None, None


class NoopSubmitter(ReviewSubmitterExtensionPoint):

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ReviewSubmitterExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def submit(self, args, review) -> None:  # noqa: D102
        pass


@pytest.fixture(scope='module', autouse=True)
def patch_get_element_analyzer_extensions():
    with patch(
        'rosdistro_reviewer.element_analyzer.get_element_analyzer_extensions',
        return_value={'noop': NoopAnalyzer()},
    ) as get_element_analyzer_extensions:
        yield get_element_analyzer_extensions


@pytest.fixture(scope='module', autouse=True)
def patch_get_review_submitter_extensions():
    with patch(
        'rosdistro_reviewer.submitter.get_review_submitter_extensions',
        return_value={'noop': NoopSubmitter()},
    ) as get_review_submitter_extensions:
        yield get_review_submitter_extensions


def test_verb_review(empty_repo):
    extension = ReviewVerb()
    extension.add_arguments(parser=Mock())

    context = CommandContext(
        command_name='rosdistro-reviewer',
        args=Mock())

    with patch(
        'rosdistro_reviewer.verb.review.Path.cwd',
        return_value=Path(empty_repo.working_tree_dir),
    ):
        assert 0 == extension.main(context=context)


def test_verb_review_no_repo(tmp_path):
    extension = ReviewVerb()
    extension.add_arguments(parser=Mock())

    context = CommandContext(
        command_name='rosdistro-reviewer',
        args=Mock())

    with patch(
        'rosdistro_reviewer.verb.review.Path.cwd',
        return_value=tmp_path,
    ):
        with pytest.raises(RuntimeError):
            extension.main(context=context)
