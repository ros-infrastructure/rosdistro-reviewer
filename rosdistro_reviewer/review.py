# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from collections import namedtuple
from enum import IntEnum
import itertools
import os
from pathlib import Path
import re
import sys
import textwrap
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union


def _should_use_color() -> bool:
    if os.environ.get('NO_COLOR'):
        return False
    elif os.environ.get('FORCE_COLOR'):
        return True
    elif os.environ.get('TERM') == 'dumb':
        return False
    else:
        return (
            sys.stdout.isatty()
            if hasattr(sys.stdout, 'isatty')
            else False
        )


def _printed_len(text: str) -> int:
    stripped = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    return len(stripped) + sum(
        stripped.count(r.as_symbol()) for r in Recommendation
    )


def _text_wrap(orig: str, width: int) -> List[str]:
    stripped = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', orig)
    if len(stripped) <= width:
        return [orig]

    match = re.match(r'^(\s*[-*] )', orig)
    subsequent_indent = ' ' * len(match.group(1) if match else '')
    return textwrap.wrap(
        orig, width=width, subsequent_indent=subsequent_indent,
    ) or ['']


def _bubblify_text(
    text: Union[str, List[str]],
    width: int = 78,
    *,
    color: Optional[int] = None,
    border_color: Optional[int] = None,
) -> str:
    norm_color = f'\033[{color}m' if color is not None else None
    norm_border_color = (
        f'\033[{border_color}m' if border_color is not None else None
    )

    top_border = '/' + ('—' * (width - 2)) + '\\'
    result = (
        f'{norm_border_color}{top_border}\033[0m'
        if norm_border_color
        else top_border
    )

    if not isinstance(text, list):
        text = [text]

    text_width = width - 4
    for idx, segment in enumerate(text):
        if idx:
            mid_sep = '+' + ('-' * (width - 2)) + '+'
            result += '\n' + (
                f'{norm_border_color}{mid_sep}\033[0m'
                if norm_border_color
                else mid_sep
            )
        for line in segment.splitlines():
            for chunk in _text_wrap(line, text_width):
                padding = ' ' * (text_width - _printed_len(chunk))

                if norm_border_color:
                    left = f'{norm_border_color}|\033[0m '
                    right = f' {norm_border_color}|\033[0m'
                else:
                    left = '| '
                    right = ' |'

                if norm_color:
                    colored_chunk = chunk.replace(
                        '\033[0m', f'\033[0m{norm_color}'
                    )
                    content = f'{norm_color}{colored_chunk}{padding}\033[0m'
                else:
                    content = chunk + padding

                result += '\n' + left + content + right

    bot_border = '\\' + ('—' * (width - 2)) + '/'
    result += '\n' + (
        f'{norm_border_color}{bot_border}\033[0m'
        if norm_border_color
        else bot_border
    )

    return result


def _format_code_block(
    file: str,
    lines: range,
    width: int,
    root: Optional[Path] = None,
    colored: bool = False,
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
            if colored:
                result += f'\n  \033[90m{num:>{digits}} |\033[0m '
            else:
                result += f'\n  {num:>{digits}} | '
            result += line[:width - digits - 5].rstrip()

    return result


class Recommendation(IntEnum):
    """Singular recommendations a review can make."""

    CRITICAL = -1
    DISAPPROVE = 0
    NEUTRAL = 1
    APPROVE = 2

    def as_symbol(self) -> str:
        """Convert the recommendation to a unicode symbol."""
        return {
            Recommendation.CRITICAL: '\U0001F6D1',
            Recommendation.DISAPPROVE: '\U0000274C',
            Recommendation.NEUTRAL: '\U0001F4DD',
            Recommendation.APPROVE: '\U00002705',
        }[self]

    def as_text(self, colored: bool = False) -> str:
        """Convert the recommendation to a shot text summary."""
        text = {
            Recommendation.CRITICAL: 'Changes required',
            Recommendation.DISAPPROVE: 'Changes recommended',
            Recommendation.NEUTRAL: 'No changes recommended, '
                                    'but requires further review',
            Recommendation.APPROVE: 'No changes recommended',
        }[self]
        if colored:
            color_code = {
                Recommendation.CRITICAL: '\033[1;31m',
                Recommendation.DISAPPROVE: '\033[1;31m',
                Recommendation.NEUTRAL: '\033[1;33m',
                Recommendation.APPROVE: '\033[1;32m',
            }[self]
            return f'{color_code}{text}\033[0m'
        return text


Annotation = namedtuple('Annotation', ('file', 'lines', 'message'))


Criterion = namedtuple('Criterion', ('recommendation', 'rationale'))


class Review:
    """High-level representation of a rosdistro code review."""

    def __init__(self, *, head_ref: Optional[str] = None):
        """
        Initialize a new instance of a Review.

        :param head_ref: The git ref where the changes have been made
        """
        self._annotations: List[Annotation] = []
        self._elements: Dict[str, List[Criterion]] = {}
        self._head_ref = head_ref

    @property
    def annotations(self) -> List[Annotation]:
        """Get the list of code annotations."""
        return self._annotations

    @property
    def elements(self) -> Dict[str, List[Criterion]]:
        """Get the mapping of element name to criteria collection."""
        return self._elements

    @property
    def head_ref(self) -> Optional[str]:
        """Get the git ref where the changes have been made."""
        return self._head_ref

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

    def to_text(
        self,
        *,
        width: int = 80,
        root: Optional[Path] = None,
        colored: Optional[bool] = None,
    ) -> str:
        """
        Generate a text representation of this review.

        :param width: Maximum number of columns in the output.
        :param root: Path to where code annotations can be resolved to. Used
          to prepend annotations with snippets of the code they refer to.
        :param colored: Whether to colorize the output. If `None`, colors will
          be auto-detected based on the environment and terminal.
        :returns: A string containing the text representation of the review.
        """
        if colored is None:
            colored = _should_use_color()

        message = self.summarize()
        recommendation = self.recommendation

        rec_text = recommendation.as_text(colored=colored)
        result = textwrap.indent(
            f' {recommendation.as_symbol()} {rec_text}\n' +
            _bubblify_text(message, width=width - 2),
            ' ')

        grouped_annotations: Dict[Tuple[str, range], List[str]] = {}
        for annotation in self.annotations:
            key = (annotation.file, annotation.lines)
            grouped_annotations.setdefault(key, []).append(annotation.message)

        for (file, lines), messages in grouped_annotations.items():
            result += '\n' + textwrap.indent(
                '\n' + _bubblify_text([
                    _format_code_block(
                        file,
                        lines,
                        width=width - 9,
                        root=root,
                        colored=colored),
                    *messages,
                ], width=width - 5, border_color=90 if colored else None),
                '  ¦ ', predicate=lambda _: True)

        return result
