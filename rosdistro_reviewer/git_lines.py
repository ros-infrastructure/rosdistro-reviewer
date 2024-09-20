# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os.path
from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence

from git import Repo
import unidiff


def _rangeify(sequence: Iterable[int]) -> Iterable[range]:
    chunk_last = None
    chunk_start = None

    for item in sequence:
        if chunk_last != item - 1:
            if chunk_start is not None:
                yield range(chunk_start, chunk_last + 1)
            chunk_start = item
        chunk_last = item

    if chunk_start is not None and chunk_last is not None:
        yield range(chunk_start, chunk_last + 1)


def get_added_lines(
    path,
    *,
    target_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
    paths=None,
) -> Optional[Mapping[str, Sequence[range]]]:
    """
    Determine what lines were added between two git repository states.

    :param path: The path to the repository root
    :param target_ref: The git ref to base the diff from
    :param head_ref: The git ref where the changes have been made
    :param paths: Relative paths under the repository to limit results to

    :returns: Mapping of relative file paths to sequences of line number
        ranges, or None if no changes were detected
    """
    with Repo(path) as repo:
        if head_ref is not None:
            head = repo.commit(head_ref)
        else:
            head = None

        if target_ref is not None:
            target = repo.commit(target_ref)
        elif head is not None:
            target = head.parents[0]
        else:
            target = repo.head.commit

        if head is not None:
            for base in repo.merge_base(target, head):
                if base is not None:
                    break
            else:
                raise RuntimeError(
                    f"No merge base found between '{target_ref}' and "
                    f"'{head_ref}'")
        else:
            base = target

        diffs = base.diff(head, paths, True)

        lines: Dict[str, List[int]] = {}
        for diff in diffs:
            if not diff.b_path:
                continue
            patch = f"""--- {diff.a_path if diff.a_path else '/dev/null'}
+++ {diff.b_path}
{diff.diff.decode()}"""
            patchset = unidiff.PatchSet(patch)
            for file in patchset:
                for hunk in file:
                    for line in hunk:
                        if line.line_type != unidiff.LINE_TYPE_ADDED:
                            continue
                        lines.setdefault(
                            os.path.normpath(file.path),
                            []).append(line.target_line_no)

    if not lines:
        return None

    return {
        path: list(_rangeify(sorted(lines.get(path, ()))))
        for path in (paths if paths is not None else lines.keys())
    }
