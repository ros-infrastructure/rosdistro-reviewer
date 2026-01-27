# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from rosdistro_reviewer.element_analyzer.multidistro import MultiDistroAnalyzer
from rosdistro_reviewer.review import Recommendation


def test_multidistro_check():
    analyzer = MultiDistroAnalyzer()

    # Case 1: No checks run when no changes
    with patch('rosdistro_reviewer.element_analyzer.multidistro.get_added_lines') as mock_get_lines:
        mock_get_lines.return_value = {}
        criteria, annotations = analyzer.analyze(Path('.'))
        assert criteria is None
        assert annotations is None

    # Case 2: Single distro change (ignored)
    with patch('rosdistro_reviewer.element_analyzer.multidistro.get_added_lines') as mock_get_lines:
        mock_get_lines.return_value = {
            'rolling/distribution.yaml': [range(1, 2)]
        }
        criteria, annotations = analyzer.analyze(Path('.'))
        assert criteria is None
        assert annotations is None

    # Case 3: Multiple distro changes (flagged)
    with patch('rosdistro_reviewer.element_analyzer.multidistro.get_added_lines') as mock_get_lines:
        mock_get_lines.return_value = {
            'rolling/distribution.yaml': [range(1, 2)],
            'iron/distribution.yaml': [range(3, 4)],
        }
        criteria, annotations = analyzer.analyze(Path('.'))
        assert criteria is not None
        assert annotations is not None
        assert len(criteria) == 1
        assert len(annotations) == 2
        assert criteria[0].recommendation == Recommendation.DISAPPROVE
        assert 'Changes to multiple distributions' in criteria[0].rationale

    # Case 4: Changes to non-distribution files (ignored)
    with patch('rosdistro_reviewer.element_analyzer.multidistro.get_added_lines') as mock_get_lines:
        mock_get_lines.return_value = {
            'rolling/release.yaml': [range(1, 2)],
            'iron/source.yaml': [range(3, 4)],
        }
        criteria, annotations = analyzer.analyze(Path('.'))
        assert criteria is None
        assert annotations is None
