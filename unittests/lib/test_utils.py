"""Unit tests for the utils module."""

from __future__ import annotations

import logging
import time
from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING, Any

import pytest
from netaddr.core import AddrFormatError

from boardfarm3.lib.utils import (
    disable_logs,
    get_nth_mac_address,
    get_pytest_name,
    get_static_ipaddress,
    get_value_from_dict,
    ip_pool_to_list,
    retry,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _retry_example(value: Any) -> Any:
    """Support method to perform retry.

    :param value: supplied value
    :type value: Any

    :return: value passed
    :rtype: Any
    """
    return value


def test_get_nth_mac_address_valid_mac() -> None:
    """Ensure that nth entry from mac adress is retrieved."""
    assert get_nth_mac_address("68:02:b8:47:fc:50", 2) == "68:02:b8:47:fc:52"


def test_get_nth_mac_address_invalid_mac() -> None:
    """Ensure that an AddrFormatError error is thrown when an invalid mac address is passed."""
    with pytest.raises(AddrFormatError):
        get_nth_mac_address("XX:XX:XX:XX:XX:XX", 2)


def test_get_pytest_name_return_current_test() -> None:
    """Ensure that the current pytest name retrieved is the correct one."""
    assert get_pytest_name() == "test_get_pytest_name_return_current_test_(call)"


@pytest.mark.parametrize(
    ("ip_range_start", "ip_range_end", "expected_ip_pool_list"),
    [
        (
            IPv4Address("192.168.1.1"),
            IPv4Address("192.168.1.5"),
            [
                IPv4Address("192.168.1.1"),
                IPv4Address("192.168.1.2"),
                IPv4Address("192.168.1.3"),
                IPv4Address("192.168.1.4"),
                IPv4Address("192.168.1.5"),
            ],
        ),
        (
            IPv6Address("8a21:1d8f:a921:804f:21a1:0867:2e4a:0000"),
            IPv6Address("8a21:1d8f:a921:804f:21a1:0867:2e4a:0005"),
            [
                IPv6Address("8a21:1d8f:a921:804f:21a1:867:2e4a:0"),
                IPv6Address("8a21:1d8f:a921:804f:21a1:867:2e4a:1"),
                IPv6Address("8a21:1d8f:a921:804f:21a1:867:2e4a:2"),
                IPv6Address("8a21:1d8f:a921:804f:21a1:867:2e4a:3"),
                IPv6Address("8a21:1d8f:a921:804f:21a1:867:2e4a:4"),
                IPv6Address("8a21:1d8f:a921:804f:21a1:867:2e4a:5"),
            ],
        ),
    ],
)
def test_ip_pool_to_list_valid_ipv4_n_ipv6_address_ranges(
    ip_range_start: IPv4Address | IPv6Address,
    ip_range_end: IPv4Address | IPv6Address,
    expected_ip_pool_list: list[IPv4Address | IPv6Address],
) -> None:
    """Ensure that valid ip pools are returned for given ip ranges.

    :param ip_range_start: ip range start
    :type ip_range_start: IPv4Address | IPv6Address
    :param ip_range_end: ip range end
    :type ip_range_end: IPv4Address | IPv6Address
    :param expected_ip_pool_list: list of ip's for the given ip range
    :type expected_ip_pool_list: list[IPv4Address | IPv6Address]
    """
    assert expected_ip_pool_list == ip_pool_to_list(ip_range_start, ip_range_end)


def test_retry_valid_string_output(mocker: MockerFixture) -> None:
    """Ensure that a valid output is returned from a method on retry.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    """
    mocker.patch.object(time, attribute="sleep", return_value=None)
    assert retry(_retry_example, 1, "out") == "out"


def test_retry_valid_boolean_true_output(mocker: MockerFixture) -> None:
    """Ensure that a valid output is returned from a method after multiple retries.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    """
    mocker.patch.object(time, attribute="sleep", return_value=None)
    assert retry(_retry_example, 2, True)


def test_retry_valid_string_false_output(mocker: MockerFixture) -> None:
    """Ensure that False is returned from a method after multiple failed retries.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    """
    mocker.patch.object(time, attribute="sleep", return_value=None)
    assert retry(_retry_example, 2, "False") == "False"


def test_retry_valid_string_bool_false_output(mocker: MockerFixture) -> None:
    """Ensure that boolen False is returned from a method after multiple failed retries.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    """
    mocker.patch.object(time, attribute="sleep", return_value=None)
    assert retry(_retry_example, 2, False) is False


@pytest.mark.parametrize(
    ("key", "input_dictionary", "expected_value"),
    [
        (1, {1: "mercury", 2: "venus"}, "mercury"),
        (
            "voltage",
            {
                "samsung": {"status": "on", "voltage": "5v"},
                "sony": {"status": "off", "voltage": "0v"},
            },
            "5v",
        ),
        (3, {1: "mercury", 2: "venus"}, None),
    ],
)
def test_get_value_from_dict_returns_string_dict_none_values(
    key: int | str,
    input_dictionary: dict[int | str, str | dict[str, str]],
    expected_value: str | None,
) -> None:
    """Ensure that the method returns all type of value for the passed key of dictionary.

    :param key: dictionary key
    :type key: int | str
    :param input_dictionary: input dictionary
    :type input_dictionary: dict[int | str, str | dict[str, str]]
    :param expected_value: value of given key from input dictionary
    :type expected_value: str | None
    """
    assert expected_value == get_value_from_dict(key, input_dictionary)


def test_disable_logs_logs_are_disabled() -> None:
    """Ensure that the logger can be disabled."""
    logger = logging.getLogger("test_logger")
    logger.handlers = [logging.StreamHandler()]
    with disable_logs("test_logger"):
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.NullHandler)


def test_disable_logs_no_logger_provided() -> None:
    """Ensure that the default logger is disabled when no logger supplied."""
    with disable_logs():
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], logging.NullHandler)


@pytest.mark.parametrize(
    ("ip_version", "config", "expected_ip"),
    [
        (
            "ipv4",
            {
                "options": "wan-static-ip:192.168.1.10,wan-static-ipv6:2001:db8::1",
            },
            "192.168.1.10",
        ),
        (
            "ipv6",
            {
                "options": "wan-static-ip:192.168.1.10,wan-static-ipv6:2001:db8::1",
            },
            "2001:db8::1",
        ),
        (
            "",
            {
                "options": "wan-dhcp",
            },
            None,
        ),
        (
            "ipv4",
            {
                "options": "",
            },
            None,
        ),
        (
            "ipv4",
            {
                "options": "wan-dhcp,wan-static-ipv6:2001:db8::1",
            },
            None,
        ),
    ],
)
def test_get_static_ipaddress(
    ip_version: str,
    config: dict[str, str],
    expected_ip: str,
) -> None:
    """Ensure that a static ip is created for given ip version and configuration.

    :param ip_version: ip version
    :type ip_version: str
    :param config: ip configuration
    :type config: dict[str, str]
    :param expected_ip: expected ip
    :type expected_ip: str
    """
    assert expected_ip == get_static_ipaddress(config, ip_version)


def test_get_static_ipaddress_invalid_config_no_options() -> None:
    """Ensure that a KeyError is raised when an invalid ip configuration is passed to get a static ip."""
    config = {
        "some_other_key": "some_value",
    }
    with pytest.raises(KeyError):
        get_static_ipaddress(config)
