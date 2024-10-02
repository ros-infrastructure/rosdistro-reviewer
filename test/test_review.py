# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
from pathlib import Path

from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation
from rosdistro_reviewer.review import Review


def test_to_text():
    review = Review()
    text = review.to_text()
    assert Recommendation.NEUTRAL.as_text() in text

    review.annotations.append(Annotation(
        file=__file__,
        lines=range(2, 3),
        message='Here is the license'))
    review.annotations.append(Annotation(
        file=__file__,
        lines=range(1, 3),
        message='Here is the whole header'))
    review.elements['foo'] = [
        Criterion(
            recommendation=Recommendation.APPROVE,
            rationale='Things look great'),
    ]

    text = review.to_text()
    assert 'Here is the license' in text
    assert 'Here is the whole header' in text
    assert 'foo' in text
    assert Recommendation.APPROVE.as_text() in text
    assert 'Things look great' in text

    review.elements['bar'] = [
        Criterion(
            recommendation=Recommendation.DISAPPROVE,
            rationale='This is a pretty long string, which should force the '
                      'line wrapping in the text formatting code to wrap it '
                      'to the bounding box width.'),
    ]
    review.annotations.append(Annotation(
        file=os.path.dirname(__file__),
        lines=range(1, 2),
        message='This annotates a file which does not exist'))

    text = review.to_text(root=Path())
    assert 'annotates a file' in text
    assert 'bar' in text
    assert Recommendation.DISAPPROVE.as_text() in text
    assert 'wrapping' in text
