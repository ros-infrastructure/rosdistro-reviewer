# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from colcon_core.generic_decorator import GenericDecorator
from colcon_core.plugin_system import satisfies_version
import pytest
from rosdistro_reviewer.element_analyzer import analyze
from rosdistro_reviewer.element_analyzer import ElementAnalyzerExtensionPoint
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation
import yaml


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


class YamlParsingAnalyzer(ElementAnalyzerExtensionPoint):

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
        for yaml_file in path.rglob('*.yaml'):
            with yaml_file.open('r') as f:
                stream = GenericDecorator(
                    f, name=str(yaml_file.relative_to(path)))
                yaml.load(stream, yaml.SafeLoader)
        return None, None


def test_analyze(empty_repo):
    path = Path(empty_repo.working_tree_dir)

    review = analyze(path, extensions={})

    assert review is None

    empty_repo.index.commit('Empty commit')

    review = analyze(
        path, extensions={}, target_ref='HEAD~1', head_ref='HEAD')

    assert review is None


def test_analyze_bad_yaml(empty_repo):
    path = Path(empty_repo.working_tree_dir)

    (path / 'sub').mkdir()
    (path / 'sub' / 'bad.yaml').write_text(
        'alpha:\n'
        '  bravo: [@charlie]\n'
        'delta: 1\n'
        '\n')
    empty_repo.index.add(['sub/bad.yaml'])

    extensions = {
        'yaml_parsing': YamlParsingAnalyzer(),
    }
    review = analyze(path, extensions=extensions)

    assert review
    assert review.recommendation == Recommendation.CRITICAL
    assert len(review.annotations) == 1
    assert review.annotations[0].file == str(Path('sub/bad.yaml'))

    empty_repo.index.add(['sub/bad.yaml'])
    empty_repo.index.commit('Add bad YAML')

    review = analyze(
        path, extensions=extensions, target_ref='HEAD~1', head_ref='HEAD')

    assert review
    assert review.recommendation == Recommendation.CRITICAL
    assert len(review.annotations) == 1
    assert review.annotations[0].file == str(Path('sub/bad.yaml'))


def test_analyze_bad_yaml_after(empty_repo):
    path = Path(empty_repo.working_tree_dir)

    (path / 'sub').mkdir()
    (path / 'sub' / 'bad.yaml').write_text(
        'alpha:\n'
        '  bravo: [charlie]\n'
        'delta: 1\n'
        '\n')
    empty_repo.index.add(['sub/bad.yaml'])
    empty_repo.index.commit('Add good YAML')

    (path / 'sub' / 'bad.yaml').write_text(
        'alpha:\n'
        '  bravo: [charlie\n'
        'delta: 1\n'
        '\n')

    extensions = {
        'yaml_parsing': YamlParsingAnalyzer(),
    }
    review = analyze(path, extensions=extensions)

    assert review
    assert review.recommendation == Recommendation.CRITICAL
    assert len(review.annotations) == 1
    assert review.annotations[0].file == str(Path('sub/bad.yaml'))

    empty_repo.index.add(['sub/bad.yaml'])
    empty_repo.index.commit('Add bad YAML')

    review = analyze(
        path, extensions=extensions, target_ref='HEAD~1', head_ref='HEAD')

    assert review
    assert review.recommendation == Recommendation.CRITICAL
    assert len(review.annotations) == 1
    assert review.annotations[0].file == str(Path('sub/bad.yaml'))


def test_analyze_bad_yaml_unrelated(empty_repo):
    path = Path(empty_repo.working_tree_dir)

    (path / 'sub').mkdir()
    (path / 'sub' / 'bad.yaml').write_text(
        'alpha:\n'
        '  bravo: [@charlie]\n'
        'delta: 1\n'
        '\n')
    empty_repo.index.add(['sub/bad.yaml'])
    empty_repo.index.commit('Add bad YAML')

    (path / 'sub' / 'bad.yaml').write_text(
        'alpha:\n'
        '  bravo: [@charlie]\n'
        'delta: 1\n'
        'echo: true\n'
        '\n')

    extensions = {
        'yaml_parsing': YamlParsingAnalyzer(),
    }
    with pytest.raises(yaml.error.MarkedYAMLError) as exc_info:
        analyze(path, extensions=extensions)

    assert exc_info.value.problem_mark is not None
    assert exc_info.value.problem_mark.name == str(Path('sub/bad.yaml'))

    empty_repo.index.add(['sub/bad.yaml'])
    empty_repo.index.commit('Add unrelated change')

    with pytest.raises(yaml.error.MarkedYAMLError) as exc_info:
        analyze(
            path, extensions=extensions, target_ref='HEAD~1', head_ref='HEAD')

    assert exc_info.value.problem_mark is not None
    assert exc_info.value.problem_mark.name == str(Path('sub/bad.yaml'))


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
