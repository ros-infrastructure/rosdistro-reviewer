# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from colcon_core.plugin_system import instantiate_extensions
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation
from rosdistro_reviewer.review import Review
import yaml


class ElementAnalyzerExtensionPoint:
    """
    The interface for element analyzers.

    An element analyzer extension provides criteria and annotations for
    composing a rosdistro review.
    """

    """The version of the element analyzer extension interface."""
    EXTENSION_POINT_VERSION = '1.0'

    def analyze(
        self,
        path: Path,
        target_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
    ) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:
        """
        Perform analysis to collect criteria and annotations.

        The method is intended to be overridden in a subclass.

        :param path: Path on disk to the git repository
        :param target_ref: The git ref to base the diff from
        :param head_ref: The git ref where the changes have been made
        :returns: A tuple with a list of criteria and a list of
          annotations
        """
        raise NotImplementedError()


def get_element_analyzer_extensions(
    *,
    group_name: Optional[str] = None,
) -> Dict[str, ElementAnalyzerExtensionPoint]:
    """
    Get the available element analyzers extensions.

    :param group_name: Optional extension point group name override
    :rtype: Dict
    """
    if group_name is None:
        group_name = __name__
    return instantiate_extensions(group_name)


def analyze(
    path: Path,
    *,
    extensions: Optional[Dict[str, ElementAnalyzerExtensionPoint]] = None,
    target_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> Optional[Review]:
    """
    Invoke each analyzer and construct a rosdistro review.

    :param path: Path on disk to the git repository
    :param extensions: The element analyzer extensions to use, if `None` is
      passed use the extensions provided by
      :func:`get_element_analyzer_extensions`
    :param target_ref: The git ref to base the diff from
    :param head_ref: The git ref where the changes have been made
    :returns: A new review instance, or None if no
      analyzer extensions performed any analysis
    """
    # We delay this import until after the GitPython
    # logger has already been configured to avoid DEBUG
    # messages on the console at import time
    from git import Repo
    if extensions is None:
        extensions = get_element_analyzer_extensions()
    if target_ref or head_ref:
        # Resolve the target_ref and head_ref from a commit-ish
        # to an actual SHA
        with Repo(path) as repo:
            if target_ref:
                target_ref = repo.commit(target_ref).hexsha
            if head_ref:
                head_ref = repo.commit(head_ref).hexsha
    review = Review(head_ref=head_ref)
    for analyzer_name, extension in extensions.items():
        try:
            criteria, annotations = extension.analyze(
                path, target_ref, head_ref)
        except yaml.error.MarkedYAMLError as e:
            criteria, annotations = analyze_yaml_error(
                e, path, target_ref, head_ref)
            if not criteria and not annotations:
                # If we can't represent the error as part of the review, let
                # the exception bubble up so the error isn't lost.
                raise

        if criteria:
            element = review.elements.setdefault(analyzer_name, [])
            for criterion in criteria:
                if criterion not in element:
                    element.append(criterion)

        for annotation in annotations or ():
            if annotation not in review.annotations:
                review.annotations.append(annotation)

    if not review.elements and not review.annotations:
        return None

    return review


def analyze_yaml_error(
    exception: yaml.error.MarkedYAMLError,
    path: Path,
    target_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:
    """
    Analyze a MarkedYAMLError and return review criteria and annotations.

    :param exception: The underlying YAML error
    :param path: Path on disk to the git repository
    :param target_ref: The git ref to base the diff from
    :param head_ref: The git ref where the changes have been made
    :returns: A tuple with a list of criteria and a list of
      annotations, or (None, None) if a review can't be generated
    """
    if not exception.problem_mark or not exception.problem_mark.name:
        return None, None
    yaml_path = exception.problem_mark.name
    error_line = exception.problem_mark.line + 1

    # We delay this import until after the GitPython
    # logger has already been configured to avoid DEBUG
    # messages on the console at import time
    from rosdistro_reviewer.git_lines import get_added_lines

    added_lines = get_added_lines(
        path,
        target_ref=target_ref,
        head_ref=head_ref,
        paths=[yaml_path])
    for lines in (added_lines or {}).get(yaml_path, ()):
        if error_line in lines:
            error_lines = range(error_line, error_line + 1)
            break
        elif error_line - 1 in lines:
            # It is a common pattern that mistakes in YAML will only manifest
            # as a syntax error on the following line. If the line wasn't
            # modified but the line before it was, it is highly likely that
            # changes on the line before caused the error. Either way, the
            # line immediately after a change is considered part of the
            # context of the review and should allow annotation.
            error_lines = range(error_line - 1, error_line + 1)
            break
    else:
        return None, None

    reason = 'A YAML syntax error is blocking analysis'
    criteria = [
        Criterion(Recommendation.CRITICAL, reason),
    ]
    msg = f'YAML parsing error: {exception.problem}'
    if exception.context:
        msg += f' ({exception.context})'
    annotations = [
        Annotation(yaml_path, error_lines, msg),
    ]

    return criteria, annotations
