"""Jenkins lockable-resources client library."""

import logging
from functools import wraps
from typing import Optional
from urllib.parse import urlencode

import requests
from requests.exceptions import ConnectTimeout, HTTPError, ReadTimeout
from requests.models import Response

_REQ_RETRY_LIMIT = 3
logger = logging.getLogger("bft")


def retry_on_timeout(func):
    """Retry decorator to retry request on timeout."""

    @wraps(func)
    def func_wrapper(*args, **kwargs):
        for i in range(1, _REQ_RETRY_LIMIT):
            try:
                return func(*args, **kwargs)
            except (ConnectTimeout, ReadTimeout) as e:
                logger.error(f"HTTP Request failed due to: {e}")
                logger.info(f"Retrying request - Attempt #{i}")
        return func(*args, **kwargs)

    return func_wrapper


class LockableResources:
    """Jenkins lockable-resources client class."""

    def __init__(self, jenkins_url: str, username: str, auth_token: str):
        """Lockable resources constructor.

        Args:
            jenkins_url (str): Jenkins URL
            username (str): Jenkins username
            auth_token (str): Jenkins authentication token
        """
        self._username: str = username
        self._auth_token: str = auth_token
        if jenkins_url[-1] != "/":
            jenkins_url += "/"
        self._jenkins_url: str = jenkins_url
        self._endpoint = "lockable-resources"

    def _verify_response(self, response: Response):
        if response.status_code != 200:
            raise HTTPError(
                f"Invalid response code: {response.status_code}\n"
                f"Response text: \n{response.text}"
            )

    @retry_on_timeout
    def _post_and_verify(self, url: str) -> Response:
        response = requests.post(
            f"{self._jenkins_url}{url}",
            auth=(self._username, self._auth_token),
        )
        self._verify_response(response)
        return response

    def acquire(
        self,
        resource: str,
        job: Optional[str],
        build: Optional[str],
        board_type: str,
    ) -> str:
        """Aquire a Jenkins lockable resource.
        Either resource of label should be present in function call

        Args:
            resource (str): Resource name
            job (str): Jenkins job name
            build (str): Jenkins build number
            board_type (str): Board type
        Returns:
            str: Name of the resource
        """
        args = {
            "resource": resource,
            "job": job,
            "build": build,
        }
        args = urlencode(
            {key: value for key, value in args.items() if value is not None}
        )
        response = self._post_and_verify(f"{self._endpoint}/acquire?{args}").json()
        resource_name = response.get("resource")
        # Handle WiFi enclosure resource with multiple boards. Based on the
        # board type we need to pick the board mentioned in resource name
        # Sample Enclosure: wifi-enclosure [CH7465LG-1-1, F3896LG-1-2]
        if "[" in resource_name and "]" in resource_name:
            boards = resource_name[
                resource_name.index("[") + 1 : resource_name.index("]")
            ].split(",")
            board_name = None
            for board in boards:
                if board.split("-")[0] in board_type:
                    board_name = board.strip()
            if board_name is None:
                raise ValueError(
                    f"Unable to find a resource matching to {board_type} in {resource_name}"
                )
        else:
            board_name = resource_name

        return board_name, resource_name

    def update_message(self, resource: str, message: str):
        """Update lockable resource message without changing the status.

        Args:
            resource (str): Resource name
            message (str): New message
        """
        args = {"resource": resource, "message": message}
        args = urlencode(args)
        self._post_and_verify(f"{self._endpoint}/updateMessage?{args}")
