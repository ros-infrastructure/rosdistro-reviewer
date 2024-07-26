# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path

from rosdistro_reviewer.yaml_lines import AnnotatedSafeLoader
import yaml


def _get_key_and_val(data, key):
    for k, v in data.items():
        if k == key:
            return k, v
    return None, None


def test_line_numbers() -> None:
    test_resources = Path(__file__).parent / 'resources'
    test_yaml = test_resources / 'simple.yaml'
    with test_yaml.open('r') as f:
        test_data = yaml.load(f, Loader=AnnotatedSafeLoader)

    foo, foo_val = _get_key_and_val(test_data, 'foo')
    assert foo and foo.__lines__ == range(2, 3)
    assert hasattr(foo_val, '__getitem__') and \
        foo_val.__lines__ == range(3, 14)

    bar, bar_val = _get_key_and_val(foo_val, 'bar')
    assert bar and bar.__lines__ == range(3, 4)
    assert bar_val == 'baz' and bar_val.__lines__ == range(3, 4)

    qux, qux_val = _get_key_and_val(foo_val, 'qux')
    assert qux and qux.__lines__ == range(4, 5)
    assert hasattr(qux_val, '__iter__') and qux_val.__lines__ == range(4, 5)
    for item in qux_val:
        assert item.__lines__ == range(4, 5)

    corge, corge_val = _get_key_and_val(foo_val, 'corge')
    assert corge and corge.__lines__ == range(5, 6)
    assert hasattr(corge_val, '__iter__') and \
        corge_val.__lines__ == range(6, 8)
    for idx, item in enumerate(corge_val):
        assert item.__lines__ == range(6 + idx, 7 + idx)

    waldo, waldo_val = _get_key_and_val(foo_val, 'waldo')
    assert waldo and waldo.__lines__ == range(8, 9)
    assert len(waldo_val) == 231 and waldo_val.__lines__ == range(8, 13)

    fred, fred_val = _get_key_and_val(foo_val, 'fred')
    assert fred and fred.__lines__ == range(13, 14)
    assert fred_val is None
