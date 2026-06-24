# Copyright 2026 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import json
import os
from pathlib import Path
from typing import Iterable
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import responses
from rosdistro_reviewer.review import Annotation
from rosdistro_reviewer.review import Criterion
from rosdistro_reviewer.review import Recommendation
from rosdistro_reviewer.review import Review
from rosdistro_reviewer.submitter.github import GitHubSubmitter

pytestmark = pytest.mark.github

MOCK_SHA = '0123456789012345678901234567890123456789'
BASE_URL = (
    'https://api.github.com:443/repos/'
    'ros-infrastructure/rosdistro-reviewer'
)
BASE_PAYLOAD_URL = (
    'https://api.github.com/repos/'
    'ros-infrastructure/rosdistro-reviewer'
)


@pytest.fixture
def mock_responses() -> Iterable[responses.RequestsMock]:
    with responses.RequestsMock(
        assert_all_requests_are_fired=False,
    ) as mocked_requests:
        mocked_requests.add(
            responses.GET,
            BASE_URL,
            json={
                'name': 'rosdistro-reviewer',
                'full_name': 'ros-infrastructure/rosdistro-reviewer',
                'url': BASE_PAYLOAD_URL,
            },
            status=200)

        mocked_requests.add(
            responses.GET,
            f'{BASE_URL}/pulls/95',
            json={
                'number': 95,
                'url': f'{BASE_PAYLOAD_URL}/pulls/95',
            },
            status=200)

        mocked_requests.add(
            responses.GET,
            f'{BASE_URL}/pulls/95/reviews',
            json=[],
            status=200)

        mocked_requests.add(
            responses.GET,
            f'{BASE_URL}/commits/{MOCK_SHA}',
            json={
                'sha': MOCK_SHA,
                'url': f'{BASE_PAYLOAD_URL}/commits/{MOCK_SHA}',
            },
            status=200)

        mocked_requests.add(
            responses.POST,
            f'{BASE_URL}/pulls/95/reviews',
            json={'id': 789},
            status=200)

        yield mocked_requests


@pytest.fixture
def github_event_path(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterable[Path]:
    tmp_path = tmp_path_factory.mktemp('event')
    event_file = tmp_path / 'event.json'
    event_file.write_text(json.dumps({
        'pull_request': {
            'author_association': 'FIRST_TIME_CONTRIBUTOR'
        }
    }))
    with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event_file)}):
        yield event_file


@pytest.fixture(params=[MOCK_SHA, None])
def populated_review(request: pytest.FixtureRequest) -> Review:
    review = Review(head_ref=request.param)
    review.annotations.append(Annotation(
        file='some/file.txt',
        lines=range(1, 2),
        message='Single line comment'))
    review.annotations.append(Annotation(
        file='another/file.txt',
        lines=range(10, 15),
        message='Multiline comment'))
    review.elements['first_element'] = [
        Criterion(Recommendation.NEUTRAL, 'Some neutral rationale')
    ]
    review.elements['second_element'] = [
        Criterion(Recommendation.APPROVE, 'Some approve rationale')
    ]
    return review


def test_add_arguments() -> None:
    submitter = GitHubSubmitter()
    parser = Mock()
    submitter.add_arguments(parser=parser)
    parser.add_argument.assert_called()


def test_submit_no_pr(populated_review: Review) -> None:
    submitter = GitHubSubmitter()
    args = Mock()
    args.github_pull_request = None
    submitter.submit(args, populated_review)


def test_submit_invalid_pr(populated_review: Review) -> None:
    submitter = GitHubSubmitter()
    args = Mock()
    args.github_pull_request = 'invalid-format'
    with pytest.raises(ValueError):
        submitter.submit(args, populated_review)


def test_submit(
    github_event_path: Path,
    mock_responses: responses.RequestsMock,
    populated_review: Review,
) -> None:
    submitter = GitHubSubmitter()
    args = Mock()
    args.github_pull_request = 'ros-infrastructure/rosdistro-reviewer#95'

    submitter.submit(args, populated_review)

    post_calls = [
        c for c in mock_responses.calls if c.request.method == 'POST'
    ]
    assert len(post_calls) == 1

    body_payload = post_calls[0].request.body
    assert isinstance(body_payload, (str, bytes))
    post_body = json.loads(body_payload)
    assert 'Introduction' in post_body['body']


def test_submit_collaborator(
    github_event_path: Path,
    mock_responses: responses.RequestsMock,
    populated_review: Review,
) -> None:
    github_event_path.write_text(json.dumps({
        'pull_request': {
            'author_association': 'COLLABORATOR'
        }
    }))

    submitter = GitHubSubmitter()
    args = Mock()
    args.github_pull_request = 'ros-infrastructure/rosdistro-reviewer#95'

    submitter.submit(args, populated_review)

    post_calls = [
        c for c in mock_responses.calls if c.request.method == 'POST'
    ]
    assert len(post_calls) == 1

    body_payload = post_calls[0].request.body
    assert isinstance(body_payload, (str, bytes))
    post_body = json.loads(body_payload)
    assert 'Introduction' not in post_body['body']


def test_submit_followup(
    github_event_path: Path,
    mock_responses: responses.RequestsMock,
    populated_review: Review,
) -> None:
    mock_responses.replace(
        responses.GET,
        f'{BASE_URL}/pulls/95/reviews',
        json=[
            {
                'id': 456,
                'user': {'login': 'github-actions[bot]'},
                'state': 'CHANGES_REQUESTED',
                'url': f'{BASE_PAYLOAD_URL}/pulls/95/reviews/456',
                'pull_request_url': f'{BASE_PAYLOAD_URL}/pulls/95',
            }
        ],
        status=200)

    mock_responses.add(
        responses.PUT,
        f'{BASE_URL}/pulls/95/reviews/456/dismissals',
        json={'id': 456, 'state': 'DISMISSED'},
        status=200)

    submitter = GitHubSubmitter()
    args = Mock()
    args.github_pull_request = 'ros-infrastructure/rosdistro-reviewer#95'

    submitter.submit(args, populated_review)

    put_calls = [
        c for c in mock_responses.calls if c.request.method == 'PUT'
    ]
    assert len(put_calls) == 1
