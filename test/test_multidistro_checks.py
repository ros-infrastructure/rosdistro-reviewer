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

    # Case 2: Multi-distro changes but only source (ignored)
    with patch('rosdistro_reviewer.element_analyzer.multidistro.get_added_lines') as mock_get_lines, \
         patch('rosdistro_reviewer.element_analyzer.multidistro.get_changed_yaml') as mock_get_yaml, \
         patch('rosdistro_reviewer.element_analyzer.multidistro.prune_changed_yaml'):
        
        mock_get_lines.return_value = {
            'rolling/distribution.yaml': [range(1, 2)],
            'iron/distribution.yaml': [range(3, 4)],
        }
        
        # Simulate source-only changes (no 'release' key in pruned data)
        mock_get_yaml.side_effect = [
             {'rolling/distribution.yaml': {'repositories': {'repo_a': {'source': {}}}}},
             {'iron/distribution.yaml': {'repositories': {'repo_b': {'source': {}}}}}
        ]
        
        criteria, annotations = analyzer.analyze(Path('.'))
        assert criteria is None
        assert annotations is None

    # Case 3: Multi-distro release changes (flagged)
    with patch('rosdistro_reviewer.element_analyzer.multidistro.get_added_lines') as mock_get_lines, \
         patch('rosdistro_reviewer.element_analyzer.multidistro.get_changed_yaml') as mock_get_yaml, \
         patch('rosdistro_reviewer.element_analyzer.multidistro.prune_changed_yaml'):
        
        mock_get_lines.return_value = {
            'rolling/distribution.yaml': [range(1, 2)],
            'iron/distribution.yaml': [range(3, 4)],
        }
        
        # Simulate release changes
        mock_get_yaml.side_effect = [
             {'rolling/distribution.yaml': {'repositories': {'repo_a': {'release': {}}}}},
             {'iron/distribution.yaml': {'repositories': {'repo_b': {'release': {}}}}}
        ]
        
        criteria, annotations = analyzer.analyze(Path('.'))
        assert criteria is not None
        assert len(criteria) == 1
        assert criteria[0].recommendation == Recommendation.DISAPPROVE
        assert 'Binary release changes' in criteria[0].rationale

    # Case 4: Mixed changes (1 release, 1 source) - (ignored)
    with patch('rosdistro_reviewer.element_analyzer.multidistro.get_added_lines') as mock_get_lines, \
         patch('rosdistro_reviewer.element_analyzer.multidistro.get_changed_yaml') as mock_get_yaml, \
         patch('rosdistro_reviewer.element_analyzer.multidistro.prune_changed_yaml'):
        
        mock_get_lines.return_value = {
            'rolling/distribution.yaml': [range(1, 2)],
            'iron/distribution.yaml': [range(3, 4)],
        }
        
        # Simulate mixed changes
        mock_get_yaml.side_effect = [
             {'rolling/distribution.yaml': {'repositories': {'repo_a': {'release': {}}}}},
             {'iron/distribution.yaml': {'repositories': {'repo_b': {'source': {}}}}}
        ]
        
        criteria, annotations = analyzer.analyze(Path('.'))
        assert criteria is None
        assert annotations is None
