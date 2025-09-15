"""Unit tests for the Boardfarm device manager module."""

import re

import pytest
from pluggy import PluginManager
from pytest_mock import MockerFixture

from boardfarm3.devices.base_devices import BoardfarmDevice
from boardfarm3.devices.linux_tftp import LinuxTFTP
from boardfarm3.exceptions import DeviceNotFound
from boardfarm3.lib.device_manager import DeviceManager, get_device_manager
from boardfarm3.main import get_plugin_manager
from boardfarm3.templates.lan import LAN


class DummyDevice(BoardfarmDevice):
    """Dummy Boardfarm Device class for testing."""


class InvalidDevice:
    """Invalid Device class for testing."""


@pytest.fixture(scope="function", name="device_manager")
def device_manager_fixture() -> DeviceManager:
    try:
        return DeviceManager(get_plugin_manager())
    except ValueError:
        return get_device_manager()


def test_device_manager_singleton(device_manager: DeviceManager) -> None:
    """Ensure exception raised when try to instantiate DeviceManager class again.

    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    assert device_manager
    with pytest.raises(
        ValueError, match=re.escape("DeviceManager is already initialized.")
    ):
        DeviceManager(get_plugin_manager())


def test_get_device_by_type_valid_device(
    mocker: MockerFixture,
    device_manager: DeviceManager,
) -> None:
    """Verify that the expected device returned when get the device by type.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    mocker.patch.object(LinuxTFTP, attribute="__init__", return_value=None)
    plugin_list = [("tftp1", LinuxTFTP({}, None)), ("tftp2", LinuxTFTP({}, None))]
    mocker.patch.object(
        PluginManager,
        attribute="list_name_plugin",
        return_value=plugin_list,
    )
    assert plugin_list[0][1] == device_manager.get_device_by_type(LinuxTFTP)
    assert isinstance(device_manager.get_device_by_type(LinuxTFTP), LinuxTFTP)


def test_get_device_by_type_invalid_device(
    mocker: MockerFixture,
    device_manager: DeviceManager,
) -> None:
    """Ensure error is raised when try to fetch a device not present in device list.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    mocker.patch.object(LinuxTFTP, attribute="__init__", return_value=None)
    plugin_list = [("tftp1", LinuxTFTP({}, None)), ("tftp2", LinuxTFTP({}, None))]
    mocker.patch.object(
        PluginManager,
        attribute="list_name_plugin",
        return_value=plugin_list,
    )
    with pytest.raises(DeviceNotFound):
        device_manager.get_device_by_type(LAN)


def test_get_devices_by_type_valid_device(
    mocker: MockerFixture,
    device_manager: DeviceManager,
) -> None:
    """Verify the device returned is valid when get device by type.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    mocker.patch.object(LinuxTFTP, attribute="__init__", return_value=None)
    plugin_list = [("tftp1", LinuxTFTP({}, None)), ("tftp2", LinuxTFTP({}, None))]
    mocker.patch.object(
        PluginManager,
        attribute="list_name_plugin",
        return_value=plugin_list,
    )
    assert len(device_manager.get_devices_by_type(LinuxTFTP)) == 2


def test_get_devices_by_type_verify_name(
    mocker: MockerFixture,
    device_manager: DeviceManager,
) -> None:
    """Verify device names when get devices by type.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    mocker.patch.object(LinuxTFTP, attribute="__init__", return_value=None)
    plugin_list = [("tftp1", LinuxTFTP({}, None)), ("tftp2", LinuxTFTP({}, None))]
    mocker.patch.object(
        PluginManager,
        attribute="list_name_plugin",
        return_value=plugin_list,
    )
    devices = device_manager.get_devices_by_type(LinuxTFTP)
    assert "tftp1" in devices
    assert "tftp2" in devices


def test_get_devices_by_type_invalid_device(
    mocker: MockerFixture,
    device_manager: DeviceManager,
) -> None:
    """Ensure no devices are returned on invalid device by type.

    :param mocker: pytest mock object
    :type mocker: MockerFixture
    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    mocker.patch.object(LinuxTFTP, attribute="__init__", return_value=None)
    plugin_list = [("tftp1", LinuxTFTP({}, None)), ("tftp2", LinuxTFTP({}, None))]
    mocker.patch.object(
        PluginManager,
        attribute="list_name_plugin",
        return_value=plugin_list,
    )
    assert device_manager.get_devices_by_type(LAN) == {}


def test_register_device_valid_boardfarm_device(device_manager: DeviceManager) -> None:
    """Verify a new device is registered successfully.

    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    device_temp = DummyDevice({"name": "tmpdev", "type": "tmp"}, None)
    device_manager.register_device(device_temp)
    assert device_temp == get_plugin_manager().get_plugin("tmpdev")


def test_register_device_invalid_device_attribute_error(
    device_manager: DeviceManager,
) -> None:
    """Ensure error is raised when try to register a non BoardfarmDevice.

    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    invalid_device = InvalidDevice()
    with pytest.raises(
        AttributeError,
        match="'InvalidDevice' object has no attribute 'device_name'",
    ):
        device_manager.register_device(invalid_device)


def test_register_device_already_registered_error(
    device_manager: DeviceManager,
) -> None:
    """Ensure that a "ValueError" error is raised when try to register a device again.

    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    test_device = DummyDevice({"name": "test", "type": "test_device"}, None)
    device_manager.register_device(test_device)
    error_msg = "Plugin name already registered: .*"
    with pytest.raises(ValueError, match=error_msg):
        device_manager.register_device(test_device)


def test_unregister_device_registered_in_plugin(device_manager: DeviceManager) -> None:
    """Verify if a device can be un registered from plugins list.

    :param device_manager: device manager instance
    :type device_manager: DeviceManager
    """
    plugin_manager = get_plugin_manager()
    if not plugin_manager.has_plugin("dummy"):
        device_manager.register_device(
            DummyDevice({"name": "dummy", "type": "hello"}, None),
        )
    device_manager.unregister_device("dummy")
    assert not plugin_manager.has_plugin("dummy")
