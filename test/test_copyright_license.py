# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

from pathlib import Path
import sys
from typing import List

import pytest


@pytest.mark.linter
def test_copyright_license() -> None:
    missing = check_files([Path(__file__).parents[1]])
    assert not len(missing), \
        'In some files no copyright / license line was found'


def check_files(paths) -> List[Path]:
    missing = []
    for path in paths:
        if path.is_dir():
            for p in sorted(path.iterdir()):
                if p.name.startswith('.'):
                    continue
                if p.name.endswith('.py') or p.is_dir():
                    missing += check_files([p])
        if path.is_file():
            content = path.read_text()
            if not content:
                continue
            lines = content.splitlines()
            has_copyright = any(
                line.startswith('# Copyright')for line in lines)
            has_license = \
                '# Licensed under the Apache License, Version 2.0' in lines
            if not has_copyright or not has_license:
                print(
                    'Could not find copyright / license in:', path,
                    file=sys.stderr)
                missing.append(path)
            else:
                print('Found copyright / license in:', path)
    return missing
