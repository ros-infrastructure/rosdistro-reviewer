# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from collections import namedtuple
from enum import IntEnum
import itertools
from pathlib import Path
import re
import textwrap
from typing import Dict
from typing import List
from typing import Optional
from typing import Union


def _printed_len(text: str) -> int:
    return len(text) + sum(
        text.count(r.as_symbol()) for r in Recommendation
    )


def _text_wrap(orig: str, width: int) -> List[str]:
    match = re.match(r'^(\s*[-*] )', orig)
    subsequent_indent = ' ' * len(match.group(1) if match else '')
    return textwrap.wrap(
        orig, width=width, subsequent_indent=subsequent_indent,
    ) or ['']


def _bubblify_text(text: Union[str, List[str]], width: int = 78) -> str:
    result = '/' + ('—' * (width - 2)) + '\\' + ''

    if not isinstance(text, list):
        text = [text]

    text_width = width - 4
    for idx, segment in enumerate(text):
        if idx:
            result += '\n+' + ('-' * (width - 2)) + '+'
        for line in segment.splitlines():
            for chunk in _text_wrap(line, text_width):
                padding = ' ' * (text_width - _printed_len(chunk))
                result += '\n| ' + chunk + padding + ' |'

    result += '\n\\' + ('—' * (width - 2)) + '/'

    return result


def _format_code_block(
    file: str,
    lines: range,
    width: int,
    root: Optional[Path] = None,
) -> str:
    if root is None or not (root / file).is_file():
        if lines.start + 1 == lines.stop:
            return f'> In {file}, line {lines.start}'
        else:
            return f'> In {file}, lines {lines.start}-{lines.stop - 1}'

    result = f'In {file}:'
    digits = len(str(lines.stop - 1))

    with (root / file).open() as f:
        for _ in range(1, lines.start):
            f.readline()
        for num, line in enumerate(f, start=lines.start):
            if num >= lines.stop:
                break
            result += f'\n  {num:>{digits}} | '
            result += line[:width - digits - 5].rstrip()

    return result


class Recommendation(IntEnum):
    """Singular recommendations a review can make."""

    DISAPPROVE = 0
    NEUTRAL = 1
    APPROVE = 2

    def as_symbol(self) -> str:
        """Convert the recommendation to a unicode symbol."""
        return {
            Recommendation.DISAPPROVE: '\U0000274C',
            Recommendation.NEUTRAL: '\U0001F4DD',
            Recommendation.APPROVE: '\U00002705',
        }[self]

    def as_text(self) -> str:
        """Convert the recommendation to a shot text summary."""
        return {
            Recommendation.DISAPPROVE: 'Changes recommended',
            Recommendation.NEUTRAL: 'No changes recommended, '
                                    'but requires further review',
            Recommendation.APPROVE: 'No changes recommended',
        }[self]


Annotation = namedtuple('Annotation', ('file', 'lines', 'message'))


Criterion = namedtuple('Criterion', ('recommendation', 'rationale'))


class Review:
    """High-level representation of a rosdistro code review."""

    def __init__(self):
        """Initialize a new instance of a Review."""
        self._annotations = []
        self._elements = {}

    @property
    def annotations(self) -> List[Annotation]:
        """Get the list of code annotations."""
        return self._annotations

    @property
    def elements(self) -> Dict[str, List[Criterion]]:
        """Get the mapping of element name to criteria collection."""
        return self._elements

    @property
    def recommendation(self) -> Recommendation:
        """Get the overall review recommendation."""
        criteria = itertools.chain.from_iterable(self.elements.values())
        return min(
            (criterion.recommendation for criterion in criteria),
            default=Recommendation.NEUTRAL)

    def summarize(self) -> str:
        """Summarize the review elements."""
        if not self._elements:
            return '(No changes to supported elements were detected)'

        message = ''
        for idx, (element, criteria) in enumerate(self.elements.items()):
            if idx:
                message += '\n\n'
            message += f'For changes related to {element}:'
            for criterion in criteria:
                message += '\n* ' + criterion.recommendation.as_symbol()
                message += ' ' + textwrap.indent(criterion.rationale, '  ')[2:]

        return message

    def to_text(self, *, width: int = 80, root: Optional[Path] = None) -> str:
        """
        Generate a text representation of this review.

        :param width: Maximum number of columns in the output.
        :param root: Path to where code annotations can be resolved to. Used
          to prepend annotations with snippets of the code they refer to.
        :returns: A string containing the text representation of the review.
        """
        message = self.summarize()
        recommendation = self.recommendation

        result = textwrap.indent(
            f' {recommendation.as_symbol()} {recommendation.as_text()}\n' +
            _bubblify_text(message, width=width - 2),
            ' ')

        for annotation in self.annotations:
            result += '\n' + textwrap.indent(
                '\n' + _bubblify_text([
                    _format_code_block(
                        annotation.file,
                        annotation.lines,
                        width=width - 9,
                        root=root),
                    annotation.message,
                ], width=width - 5),
                '  ¦ ', predicate=lambda _: True)

        return result
