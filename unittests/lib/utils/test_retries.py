"""Unit tests for the lib.utils retry and retry_on_exception."""

# pylint: disable=missing-docstring

from typing import Any

import pytest
from pytest_mock import MockerFixture

from boardfarm3.lib.utils import retry, retry_on_exception


class HelperMethods:
    """Unittest helper class."""

    @staticmethod
    def _return_int() -> int:
        return 42

    @staticmethod
    def _return_str() -> str:
        return "story"

    @staticmethod
    def _return_none() -> None:
        return None

    @staticmethod
    def _return_false() -> bool:
        return False

    @staticmethod
    def _return_false_as_string() -> str:
        return "False"

    @staticmethod
    def raise_exception() -> None:
        """Raise a NotImplementedError exception.

        :raises NotImplementedError: Always raises this exception.
        """
        raise NotImplementedError

    @staticmethod
    def raise_exception_two_times(i: list[int]) -> int:
        """Raise NotImplementedError 2 times.

        :param i: exception counter
        :type i: list[int], optional

        :raises NotImplementedError: Raised when the counter is less than 2.

        :return: Exception count.
        :rtype: int
        """
        i[0] += 1
        if i[0] < 2:
            raise NotImplementedError
        return i[0]


@pytest.fixture(name="helper_methods")
def helper_methods_fixture(mocker: MockerFixture) -> HelperMethods:
    """Get the HelperMethods instance.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :return: HelperMethods class instance
    :rtype: HelperMethods
    """
    # patch time.sleep to avoid unnecessary sleeps in the test
    mocker.patch("time.sleep")
    return HelperMethods()


@pytest.mark.parametrize(
    ("funct_name", "exp_out", "exp_count"),
    [
        ("_return_int", 42, 1),
        ("_return_str", "story", 1),
        ("_return_none", None, 3),
        ("_return_false", False, 3),
        ("_return_false_as_string", "False", 3),
    ],
)
def test_retry_three_times(
    mocker: MockerFixture,
    helper_methods: HelperMethods,
    funct_name: str,
    exp_out: Any,
    exp_count: int,
) -> None:
    """Ensure that a method is executed a specified number of times if the method returns false.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param helper_methods: HelperMethods class instance
    :type helper_methods: HelperMethods
    :param funct_name: function name to be called
    :type funct_name: str
    :param exp_out: expected output
    :type exp_out: Any
    :param exp_count: expected count
    :type exp_count: int
    """
    spy = mocker.spy(helper_methods, funct_name)

    assert retry(getattr(helper_methods, funct_name), 3) == exp_out
    assert spy.call_count == exp_count
    assert spy.spy_return == exp_out


def test_retry_on_exception(
    mocker: MockerFixture,
    helper_methods: HelperMethods,
) -> None:
    """Ensure that a method retry is executed if the method raises an exception.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param helper_methods: HelperMethods class instance
    :type helper_methods: HelperMethods
    """
    spy = mocker.spy(helper_methods, "raise_exception")

    with pytest.raises(NotImplementedError):
        retry_on_exception(helper_methods.raise_exception, [])
    assert spy.call_count == 10
    assert spy.spy_return is None


def test_retry_on_exception_that_goes_away(
    mocker: MockerFixture,
    helper_methods: HelperMethods,
) -> None:
    """Ensure that a method retry is executed when on each exception.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param helper_methods: HelperMethods class instance
    :type helper_methods: HelperMethods
    """
    spy = mocker.spy(helper_methods, "raise_exception_two_times")
    exp_out = 2

    assert (
        retry_on_exception(helper_methods.raise_exception_two_times, [[0]]) == exp_out
    )
    assert spy.call_count == 2
    assert spy.spy_return == exp_out


@pytest.mark.parametrize(
    ("funct_name", "retries", "exp_count"),
    [
        ("raise_exception", 0, 1),
        ("raise_exception", 3, 3),
    ],
)
def test_retries_on_exception(
    mocker: MockerFixture,
    helper_methods: HelperMethods,
    funct_name: str,
    retries: int,
    exp_count: int,
) -> None:
    """Ensure that the retry occurs only a specified number of times and not more.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param helper_methods: HelperMethods class instance
    :type helper_methods: HelperMethods
    :param funct_name: function name to be called
    :type funct_name: str
    :param retries: retry count
    :type retries: int
    :param exp_count: expected count
    :type exp_count: int
    """
    spy = mocker.spy(helper_methods, funct_name)

    with pytest.raises(NotImplementedError):
        assert retry_on_exception(
            getattr(helper_methods, funct_name),
            [],
            retries=retries,
        )
    assert spy.call_count == exp_count
    assert spy.spy_return is None
