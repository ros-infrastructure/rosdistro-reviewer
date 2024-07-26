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
from rosdistro_reviewer.review import Review


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
      :function:`get_element_analyzer_extensions`
    :param target_ref: The git ref to base the diff from
    :param head_ref: The git ref where the changes have been made
    :returns: A new review instance, or None if no
      analyzer extensions performed any analysis
    """
    if extensions is None:
        extensions = get_element_analyzer_extensions()
    review = Review()
    for analyzer_name, extension in extensions.items():
        criteria, annotations = extension.analyze(path, target_ref, head_ref)

        if criteria:
            review.elements.setdefault(analyzer_name, [])
            review.elements[analyzer_name].extend(criteria)

        if annotations:
            review.annotations.extend(annotations)

    if not review.elements and not review.annotations:
        return None

    return review
