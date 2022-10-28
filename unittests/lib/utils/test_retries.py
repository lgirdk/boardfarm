"""Unit tests for the lib.utils retry and retry_on_exception."""

# pylint: disable=missing-docstring


from typing import Any

import pytest
from pytest_mock import MockerFixture

from boardfarm3.lib.utils import retry, retry_on_exception


class HelperMethods:  # noqa: D101
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
    def raise_exception() -> None:  # noqa: D102
        raise NotImplementedError

    @staticmethod
    # pylint: disable=dangerous-default-value
    def raise_exception_two_times(i: list[int] = [0]) -> int:  # noqa: D102,B006
        i[0] += 1
        if i[0] < 2:
            raise NotImplementedError
        return i[0]


@pytest.fixture(name="helper_methods")
def helper_methods_fixture(mocker: MockerFixture) -> HelperMethods:  # noqa: D103
    # patch time.sleep to avoid unnecessary sleeps in the test
    mocker.patch("time.sleep")
    return HelperMethods()


@pytest.mark.parametrize(
    "funct_name,exp_out,exp_count",
    [
        ("_return_int", 42, 1),
        ("_return_str", "story", 1),
        ("_return_none", None, 3),
        ("_return_false", False, 3),
        ("_return_false_as_string", "False", 3),
    ],
)
def test_retry_three_times(  # noqa: D103
    mocker: MockerFixture,
    helper_methods: HelperMethods,
    funct_name: str,
    exp_out: Any,
    exp_count: int,
) -> None:
    spy = mocker.spy(helper_methods, funct_name)

    assert retry(getattr(helper_methods, funct_name), 3) == exp_out
    assert spy.call_count == exp_count
    assert spy.spy_return == exp_out


def test_retry_on_exception(  # noqa: D103
    mocker: MockerFixture, helper_methods: HelperMethods
) -> None:
    spy = mocker.spy(helper_methods, "raise_exception")

    with pytest.raises(NotImplementedError):
        retry_on_exception(helper_methods.raise_exception, [])
    assert spy.call_count == 10
    assert spy.spy_return is None


def test_retry_on_exception_that_goes_away(  # noqa: D103
    mocker: MockerFixture, helper_methods: HelperMethods
) -> None:
    spy = mocker.spy(helper_methods, "raise_exception_two_times")
    exp_out = 2

    assert retry_on_exception(helper_methods.raise_exception_two_times, []) == exp_out
    assert spy.call_count == 2
    assert spy.spy_return == exp_out


@pytest.mark.parametrize(
    "funct_name,retries,exp_count",
    [
        ("raise_exception", 0, 1),
        ("raise_exception", 3, 3),
    ],
)
def test_retries_on_exception(  # noqa: D103
    mocker: MockerFixture,
    helper_methods: HelperMethods,
    funct_name: str,
    retries: int,
    exp_count: int,
) -> None:
    spy = mocker.spy(helper_methods, funct_name)

    with pytest.raises(NotImplementedError):
        assert retry_on_exception(
            getattr(helper_methods, funct_name), [], retries=retries
        )
    assert spy.call_count == exp_count
    assert spy.spy_return is None
