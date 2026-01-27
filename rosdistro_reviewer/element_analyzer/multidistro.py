# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import List
from typing import Optional
from typing import Tuple

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from rosdistro_reviewer.element_analyzer \
    import ElementAnalyzerExtensionPoint
from rosdistro_reviewer.git_lines import get_added_lines
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation

logger = colcon_logger.getChild(__name__)


class MultiDistroAnalyzer(ElementAnalyzerExtensionPoint):
    """Element analyzer for changes to multiple rosdistro distributions."""

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
        criteria: List[Criterion] = []
        annotations: List[Annotation] = []

        changes = get_added_lines(
            path, target_ref=target_ref, head_ref=head_ref)
        if not changes:
            return None, None

        distros = set()
        distro_changes = {}

        for filename in changes.keys():
            path_obj = Path(filename)
            if len(path_obj.parts) < 2:
                continue
            if path_obj.name != 'distribution.yaml':
                continue

            distros.add(path_obj.parent.name)
            distro_changes[path_obj] = changes[filename]

        if len(distros) <= 1:
            return None, None

        logger.info('Performing analysis on multi-distribution changes...')

        recommendation = Recommendation.DISAPPROVE
        message = 'Changes to multiple distributions are not allowed ' \
                  'in a single PR'

        for file_path, lines in distro_changes.items():
            annotations.append(Annotation(
                str(file_path),
                lines[0],
                'This distribution should not be modified in the same PR '
                'as others'))

        criteria.append(Criterion(recommendation, message))

        return criteria, annotations
