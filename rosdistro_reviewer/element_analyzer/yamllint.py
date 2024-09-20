# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from pathlib import PurePosixPath
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Tuple

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from git import Repo
from git.objects import Blob
from rosdistro_reviewer.element_analyzer \
    import ElementAnalyzerExtensionPoint
from rosdistro_reviewer.git_lines import get_added_lines
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation
from yamllint import linter
from yamllint.config import YamlLintConfig

logger = colcon_logger.getChild(__name__)


def _is_yaml_blob(item, depth) -> bool:
    return PurePosixPath(item.path).suffix == '.yaml'


def _get_changed_yaml(
    path: Path,
    target_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> Optional[Mapping[str, Sequence[range]]]:
    if head_ref:
        with Repo(path) as repo:
            tree = repo.tree(head_ref)
            yaml_files = [
                str(item.path)
                for item in tree.traverse(_is_yaml_blob)
                if isinstance(item, Blob)
            ]
    else:
        yaml_files = [
            str(p.relative_to(path))
            for p in path.glob('**/*.yaml')
            if p.parts[len(path.parts)] != '.git'
        ]
    if not yaml_files:
        logger.info('No YAML files were found in the repository')
        return None

    changes = get_added_lines(
        path, target_ref=target_ref, head_ref=head_ref, paths=yaml_files)
    if not changes:
        logger.info('No YAML files were modified')
        return None

    return changes


class YamllintAnalyzer(ElementAnalyzerExtensionPoint):
    """Element analyzer for linting changes to YAML files."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ElementAnalyzerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def analyze(  # noqa: D102
        self,
        path: Path,
        target_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
    ) -> Tuple[Optional[List[Criterion]], Optional[List[Annotation]]]:
        criteria: List[Criterion] = []
        annotations: List[Annotation] = []

        changed_yaml = _get_changed_yaml(path, target_ref, head_ref)
        if not changed_yaml:
            # Bypass check if no YAML files were changed
            return None, None

        logger.info('Performing analysis on YAML changes...')

        config_file = path / '.yamllint'
        if config_file.is_file():
            logger.debug(f'Using yamllint config: {config_file}')
            config = YamlLintConfig(file=str(config_file))
        else:
            logger.debug('Using default yamllint config')
            config = YamlLintConfig('extends: default')

        recommendation = Recommendation.APPROVE

        for yaml_path, lines in changed_yaml.items():
            if not lines:
                continue
            logger.debug(f'Reading {yaml_path} for yamllint')

            # It would be better to avoid reading the entire file into memory,
            # but it seems that yamllint is going to do that anyway and
            # requires that file-like objects implement IOBase, which
            # GitPython streams do not (missing readable method).
            git_yaml_path = str(PurePosixPath(Path(yaml_path)))
            if head_ref is not None:
                with Repo(path) as repo:
                    data = repo.tree(
                        head_ref
                    )[git_yaml_path].data_stream.read().decode()
            else:
                data = (path / yaml_path).read_text()
            for problem in linter.run(data, config, filepath=git_yaml_path):
                if any(problem.line in chunk for chunk in lines):
                    annotations.append(Annotation(
                        yaml_path,
                        range(problem.line, problem.line + 1),
                        'This line does not pass YAML '
                        f'linter checks: {problem.desc}'))
                    recommendation = Recommendation.DISAPPROVE

        if recommendation == Recommendation.APPROVE:
            message = 'All new lines of YAML pass linter checks'
        else:
            message = 'One or more linter violations were added to YAML files'

        criteria.append(Criterion(recommendation, message))

        return criteria, annotations
