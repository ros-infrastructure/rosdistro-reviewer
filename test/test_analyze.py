# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from rosdistro_reviewer.element_analyzer import analyze
from rosdistro_reviewer.element_analyzer import ElementAnalyzerExtensionPoint
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation


class DuplicateFeedbackAnalyzer(ElementAnalyzerExtensionPoint):

    def analyze(
        self,
        path: Path,
        target_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
    ) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:
        criteria = [
            Criterion(
                recommendation=Recommendation.APPROVE,
                rationale='Things look great'),
            Criterion(
                recommendation=Recommendation.APPROVE,
                rationale='Things look great'),
            Criterion(
                recommendation=Recommendation.DISAPPROVE,
                rationale='Some other check'),
        ]
        annotations = [
            Annotation(
                file='foo.yaml',
                lines=range(1, 2),
                message='Duplicate annotation'),
            Annotation(
                file='foo.yaml',
                lines=range(1, 2),
                message='Duplicate annotation'),
            Annotation(
                file='bar.yaml',
                lines=range(1, 2),
                message='Unique annotation'),
        ]
        return criteria, annotations


def test_analyze_deduplication() -> None:
    extensions: Dict[str, ElementAnalyzerExtensionPoint] = {
        'duplicate': DuplicateFeedbackAnalyzer()
    }
    review = analyze(Path(), extensions=extensions)
    assert review is not None

    # Check criteria de-duplication
    assert 'duplicate' in review.elements
    criteria = review.elements['duplicate']
    assert len(criteria) == 2
    assert criteria[0] == Criterion(
        recommendation=Recommendation.APPROVE,
        rationale='Things look great')
    assert criteria[1] == Criterion(
        recommendation=Recommendation.DISAPPROVE,
        rationale='Some other check')

    # Check annotations de-duplication
    assert len(review.annotations) == 2
    assert review.annotations[0] == Annotation(
        file='foo.yaml',
        lines=range(1, 2),
        message='Duplicate annotation')
    assert review.annotations[1] == Annotation(
        file='bar.yaml',
        lines=range(1, 2),
        message='Unique annotation')
