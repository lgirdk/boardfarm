"""Unit tests for Jenkins lockable resources class."""
import json

import pytest
import requests
from requests.exceptions import ConnectTimeout
from requests.models import HTTPError

from boardfarm.dbclients.lockableresources import LockableResources


class ResponseStub:
    def __init__(self, status_code, response) -> None:
        self.status_code = status_code
        self.text = response

    def json(self):
        if self.text is None:
            return None
        return json.loads(self.text)


@pytest.fixture
def lockable_resources():
    yield LockableResources("base_url", "username", "auth_token")


def test_acquire(lockable_resources, mocker):
    response = ResponseStub(200, json.dumps({"resource": "resource-a"}))
    mocker.patch("requests.post", return_value=response)
    board, resource = lockable_resources.acquire(
        resource="resource-a", job=None, build=None, board_type="any-board-type"
    )
    requests.post.assert_called_once_with(
        "base_url/lockable-resources/acquire?resource=resource-a",
        auth=("username", "auth_token"),
    )
    assert resource == board
    assert board == "resource-a"


def test_acquire_wifi_enclosure(lockable_resources, mocker):
    enclosure = "wifi-enclosure [CH7465LG-1-1, F3896LG-1-2]"
    response = ResponseStub(200, json.dumps({"resource": enclosure}))
    mocker.patch("requests.post", return_value=response)
    board, resource = lockable_resources.acquire(
        resource=enclosure, job=None, build=None, board_type="CH7465LG"
    )
    assert board != resource
    assert board == "CH7465LG-1-1"
    assert resource == enclosure


def test_acquire_wifi_enclosure_invalid_board_type(lockable_resources, mocker):
    enclosure = "wifi-enclosure [CH7465LG-1-1, F3896LG-1-2]"
    response = ResponseStub(200, json.dumps({"resource": enclosure}))
    mocker.patch("requests.post", return_value=response)
    with pytest.raises(ValueError):
        lockable_resources.acquire(
            resource=enclosure, job=None, build=None, board_type="invalid type"
        )


def test_acquire_unknow_user(lockable_resources, mocker):
    response = ResponseStub(401, "Unknow user")
    mocker.patch("requests.post", return_value=response)
    with pytest.raises(HTTPError):
        lockable_resources.acquire("resource", None, None, "any-board-type")


def test_acquire_on_timeout(lockable_resources, mocker):
    resource = {"resource": "resource-b"}
    response = ResponseStub(200, json.dumps(resource))
    mocker.patch("requests.post", side_effect=[ConnectTimeout, response])
    return_value = lockable_resources.acquire(
        resource="resource-a", job=None, build=None, board_type="any-board-type"
    )
    assert return_value == ("resource-b", "resource-b")
    assert requests.post.call_count == 2


def test_update_message(lockable_resources, mocker):
    response = ResponseStub(200, "true")
    mocker.patch("requests.post", return_value=response)
    lockable_resources.update_message("resource", "message")
    requests.post.assert_called_once_with(
        "base_url/lockable-resources/updateMessage?resource=resource&message=message",
        auth=("username", "auth_token"),
    )


def test_update_message_invalid_message(lockable_resources, mocker):
    response = ResponseStub(403, "Invalid message")
    mocker.patch("requests.post", return_value=response)
    with pytest.raises(HTTPError):
        lockable_resources.update_message("resource", "message")
