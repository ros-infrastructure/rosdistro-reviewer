# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from typing import Iterable
from typing import Mapping
from typing import Optional

from git import Repo
from rosdistro_reviewer.git_lines import get_added_lines
from rosdistro_reviewer.yaml_lines import AnnotatedSafeLoader
import yaml


def _contains(needle: Optional[range], haystack: Iterable[range]) -> bool:
    """
    Determine if a range intersects with any ranges in another group of ranges.

    :param needle: The candidate range to look for intersection with
    :param haystack: The group of other ranges to check for intersection with
    :returns: True if the candidate range intersects with at least one member
      of the other group of ranges, otherwise False.
    """
    if needle is not None:
        for straw in haystack:
            if needle.start < straw.stop and needle.stop > straw.start:
                return True
    return False


def _isolate(data, changes) -> None:
    if not hasattr(data, '__lines__'):
        return

    if not _contains(data.__lines__, changes):
        data.__lines__ = None

    if isinstance(data, list):
        for item in data:
            if hasattr(item, '__lines__'):
                if _contains(item.__lines__, changes):
                    _isolate(item, changes)
                else:
                    item.__lines__ = None

    elif isinstance(data, dict):
        for k, v in tuple(data.items()):
            if hasattr(k, '__lines__'):
                if _contains(k.__lines__, changes):
                    # If key was modified, consider everything under it to
                    # have been modified as well
                    continue
                k.__lines__ = None

            _isolate(v, changes)


def get_changed_yaml(
    path,
    paths,
    *,
    target_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> Optional[Mapping[str, Any]]:
    """
    Load YAML data with line annotations only on changed trees.

    :param path: Path on disk to the git repository
    :param paths: Repository-relative paths to YAML files to look for
      changes to
    :param target_ref: The git ref to base the diff from
    :param head_ref: The git ref where the changes have been made

    :returns: Mapping of YAML file paths to annotated YAML data,
      or None if no changes were detected
    """
    changes = get_added_lines(path, target_ref=target_ref,
                              head_ref=head_ref, paths=paths)
    if not changes:
        return None

    data = {}
    if head_ref is not None:
        with Repo(path) as repo:
            for yaml_path in paths:
                git_yaml_path = str(PurePosixPath(Path(yaml_path)))
                data[yaml_path] = yaml.load(
                    repo.tree(head_ref)[git_yaml_path].data_stream,
                    Loader=AnnotatedSafeLoader)
    else:
        for yaml_path in paths:
            with (path / yaml_path).open('r') as f:
                data[yaml_path] = yaml.load(f, Loader=AnnotatedSafeLoader)

    for yaml_path, yaml_data in data.items():
        _isolate(yaml_data, changes.get(yaml_path, ()))

    return data


def prune_changed_yaml(data: Any) -> None:
    """
    Prune sub-trees of annotated YAML data without line annotations.

    :param data: The YAML data to prune
    :returns: None
    """
    if isinstance(data, list):
        for idx, item in reversed(tuple(enumerate(data))):
            if getattr(item, '__lines__', None):
                prune_changed_yaml(item)
                continue
            del data[idx]

    elif isinstance(data, dict):
        for k, v in tuple(data.items()):
            if getattr(k, '__lines__', None):
                continue
            if getattr(v, '__lines__', None):
                prune_changed_yaml(v)
                continue

            del data[k]
