# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import yaml


class AnnotatedSafeLoader(yaml.SafeLoader):
    """
    YAML loader that adds '__lines__' attributes to some of the parsed data.

    This extension of the PyYAML SafeLoader replaces some basic types with
    derived types that include a '__lines__' attribute to determine where
    the deserialized data can be found in the YAML file it was parsed from.
    """

    class AnnotatedDict(dict):
        """Implementation of 'dict' with '__lines__' attribute."""

        __slots__ = ('__lines__',)

        def __init__(self, *args, **kwargs):  # noqa: D107
            return super().__init__(*args, **kwargs)

    class AnnotatedList(list):
        """Implementation of 'list' with '__lines__' attribute."""

        __slots__ = ('__lines__',)

        def __init__(self, *args, **kwargs):  # noqa: D107
            return super().__init__(*args, **kwargs)

    class AnnotatedStr(str):
        """Implementation of 'str' with '__lines__' attribute."""

        __slots__ = ('__lines__',)

        def __new__(cls, *args, **kwargs):  # noqa: D102
            return str.__new__(cls, *args, **kwargs)

    def compose_node(self, parent, index):  # noqa: D102
        event = self.peek_event()
        start_line = event.start_mark.line + 1
        end_line = event.end_mark.line + 1
        if end_line <= start_line:
            end_line = start_line + 1
        node = super().compose_node(parent, index)
        node.__lines__ = range(start_line, end_line)
        return node

    def construct_annotated_map(self, node):  # noqa: D102
        data = AnnotatedSafeLoader.AnnotatedDict()
        data.__lines__ = node.__lines__
        yield data
        value = self.construct_mapping(node, deep=True)
        for k, v in reversed(tuple(value.items())):
            k_lines = getattr(k, '__lines__', None)
            if k_lines is not None and k_lines.stop > data.__lines__.stop:
                data.__lines__ = range(data.__lines__.start, k_lines.stop)

            v_lines = getattr(v, '__lines__', None)
            if v_lines is not None and v_lines.stop > data.__lines__.stop:
                data.__lines__ = range(data.__lines__.start, v_lines.stop)
        data.update(value)

    def construct_annotated_seq(self, node):  # noqa: D102
        data = AnnotatedSafeLoader.AnnotatedList()
        data.__lines__ = node.__lines__
        yield data
        value = self.construct_sequence(node, deep=True)
        for v in reversed(value):
            v_lines = getattr(v, '__lines__', None)
            if v_lines is not None and v_lines.stop > data.__lines__.stop:
                data.__lines__ = range(data.__lines__.start, v_lines.stop)
        data.extend(value)

    def construct_annotated_str(self, node):  # noqa: D102
        data = self.construct_yaml_str(node)
        data = AnnotatedSafeLoader.AnnotatedStr(data)
        data.__lines__ = node.__lines__
        return data


AnnotatedSafeLoader.add_constructor(
    'tag:yaml.org,2002:map', AnnotatedSafeLoader.construct_annotated_map)
AnnotatedSafeLoader.add_constructor(
    'tag:yaml.org,2002:seq', AnnotatedSafeLoader.construct_annotated_seq)
AnnotatedSafeLoader.add_constructor(
    'tag:yaml.org,2002:str', AnnotatedSafeLoader.construct_annotated_str)

yaml.add_representer(
    AnnotatedSafeLoader.AnnotatedDict,
    yaml.representer.SafeRepresenter.represent_dict)
yaml.add_representer(
    AnnotatedSafeLoader.AnnotatedList,
    yaml.representer.SafeRepresenter.represent_list)
yaml.add_representer(
    AnnotatedSafeLoader.AnnotatedStr,
    yaml.representer.SafeRepresenter.represent_str)
