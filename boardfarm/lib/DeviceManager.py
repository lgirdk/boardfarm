#!/usr/bin/env python3
# Setup logging
"""Class functions to Manage device."""
import logging
import re
import sys
import uuid
from collections import UserList
from typing import Dict, List

from aenum import Enum, extend_enum

from boardfarm.exceptions import DeviceDoesNotExistError
from boardfarm.lib.wifi_lib import wifi_mgr
from boardfarm.lib.wrappers import singleton

logging.basicConfig(stream=sys.stdout, format="%(message)s")
logger = logging.getLogger("DeviceManager")
logger.setLevel(logging.INFO)  # DEBUG, INFO, WARNING, ERROR, CRITICAL


class DeviceNone:
    """Check device."""

    def __getattr__(self, key):
        """Raise DeviceDoesNotExistError."""
        raise DeviceDoesNotExistError


# TODO: type + name are confusing and need to be sorted out
# This is really to handle legacy types, you really should be requesting device
# by location and/or feature. E.g. wan2/lan2/etc all start to go away from this
# short list
class device_type(Enum):
    """Identifiers for different kinds of devices.

    Useful for correctly connecting to and using a device.
    """

    Unknown = 0
    DUT = 1
    board = 1
    wan = 2
    wan2 = 3
    lan = 4
    lan1 = 4
    lan2 = 5
    sipcenter = 6
    acs_server = 7
    wifi = 8
    gre = 9
    provisioner = 10
    syslog_server = 11
    ixia1 = 12
    wan_factory = 13
    lan_factory = 14
    fax_modem = 15
    fax_modem1 = 16
    fax_modem2 = 17
    wlan = 18
    wlan2 = 19
    cmts = 20
    cdrouter = 21
    booster = 22
    softphone = 23
    mac_sniffer = 24
    mitm = 25
    mini_cmts = 26
    wlan1 = 18
    wlan3 = 28
    wlan4 = 29
    softphone2 = 30
    fxs1 = 31
    fxs2 = 32
    lan3 = 33
    lan4 = 34


class device_array_type(Enum):
    """Identifiers for device array type."""

    wan_clients = 1
    lan_clients = 2
    wlan_clients = 3
    FXS = 4
    softphones = 5

    _arrays = {
        "wan_clients": [],
        "lan_clients": [],
        "wlan_clients": wifi_mgr,
        "FXS": [],
        "softphones": [],
    }


class device_location(Enum):
    """Identifiers for how a device is connected to the DUT."""

    Unknown = 0
    Northbound = 1
    WAN = 1
    Southbound = 2
    LAN = 2
    DUT = 3


class device_os(Enum):
    """Identifiers for the type of Operating System (OS) of a device."""

    Unknown = 0
    Linux = 1
    Windows = 2


# to replace linux_boot.LinuxDevice.get_device_by_feature
class device_feature(Enum):
    """Identifiers for extra features a device may have."""

    Unknown = 0
    Generic = 1
    Wifi2G = 2
    Wifi5G = 3


class device_descriptor:
    """All identifiers about a device."""

    location = device_location.Unknown
    os = device_os.Linux
    type = device_type.Unknown
    features = [device_feature.Unknown]
    obj = None

    def __str__(self):
        """Define device descriptor details."""
        ret = "==== DEVICE DESCRIPTOR ====\n"
        ret += "location = " + str(self.location) + "\n"
        ret += "os = " + str(self.os) + "\n"
        ret += "type = " + str(self.type) + "\n"
        ret += "features = " + str(self.features) + "\n"
        ret += str(self.obj)

        return ret


def get_device_by_name(name):
    mgr = device_manager()

    # check if device from an array is requested
    o = re.search(r"(.*)\[(.*)\]", name)
    if o:
        device_idx = int(o.group(2))
        array_type = o.group(1)
        return mgr.get_device_array(array_type)[device_idx]

    type_enum = getattr(device_type, name)
    if not type_enum:
        raise Exception(f"Invalid input ! device name : {name}")
    return mgr.get_device_by_type(type_enum)


@singleton
class device_manager(UserList):
    """Manages all your devices, for getting and creating (if needed)."""

    def __init__(self):
        """Instance initialisation."""
        self.name = "device_manager"
        super().__init__()
        # List of current devices, which we prefer to reuse instead of creating new ones
        self.devices: List[device_descriptor] = []
        # Devices that can create other devices, we store them for later
        # so we can use them to create devices that might not already exist
        self.factories = []
        self.plugin_counter = -1

        # TODO: does self.env really belong here or in device class?
        self.uniqid = uuid.uuid4().hex[:15]  # Random, unique ID and use first 15 bytes
        self.env = {
            "wan_iface": f"wan{self.uniqid[:12]}",
            "lan_iface": f"lan{self.uniqid[:12]}",
            "uniq_id": self.uniqid,
        }

    def register_wifi_clients(self, env_helper):
        if not getattr(self, "wlan_clients", None):
            raise DeviceDoesNotExistError("No Wi-Fi devices in setup")

        wifi_clients = env_helper.wifi_clients()
        if wifi_clients:

            # Register all wifi clients in wifi manager
            for client in wifi_clients:
                self.wlan_clients.register(client)

        self.wlan_clients.registered_clients_summary()

    @property  # type: ignore
    def data(self):
        """Get the list of obj for devices."""
        return [x.obj for x in self.devices]

    @data.setter
    def data(self, x):
        """To clear/initialize the list of devices."""
        self.devices = x

    def set_device_array(self, array_name, dev, override):
        """Set Device Array details."""
        if not getattr(device_array_type, array_name, None):
            raise Exception(f"Invalid device array type {array_name}")

        dev_array = getattr(
            self, array_name, device_array_type._arrays.value[array_name]
        )
        for i in dev_array:
            if i.ipaddr == dev.ipaddr and i.port == dev.port and not override:
                raise Exception(
                    f"Device manager has {i.name}@{i.ipaddr}:{i.port} already:"
                    f" {dev.name}@{dev.ipaddr}:{dev.port}"
                )
        dev_array.append(dev)
        setattr(self, array_name, dev_array)

    def close_all(self):
        """Close connections to all devices."""
        for d in self.devices:
            try:
                logger.debug(f"Closing connection to '{d.type.name}'.")
                d.obj.close()
            except Exception as e:
                logger.warning(e)
                logger.warning(
                    f"Problem trying to close connection to '{d.type.name}'."
                )
        # erase device list
        self.devices = []

    def by_type(self, t, num=1):
        """Shorthand for getting device by type."""
        return self.get_device_by_type(t, num)

    def by_types(self, types):
        """Shorthand for getting devices by types."""
        return self.get_devices_by_types(types)

    def get_device_by_type(self, t, num=1):
        """Get device that already exists by type."""
        return self.get_device(t, None, None, num)

    def get_device_array(self, array_type):
        if not getattr(device_array_type, array_type, None):
            raise Exception(f"Invalid device array type {array_type}")

        return getattr(self, array_type, [])

    def get_devices_by_types(self, types):
        """Get multiple devices by types."""
        return [self.by_type(t, num=1) for t in types]

    def by_feature(self, feature, num=1):
        """Shorthand for getting device by feature."""
        return self.get_device_by_feature(feature, num)

    def get_device_by_feature(self, feature, num=1):
        """Get device that already exists by feature."""
        return self.get_device(None, feature, None, num)

    def by_location(self, location, num=1):
        """Shorthand for getting device by location."""
        return self.get_device_by_location(location, num)

    def get_device_by_location(self, location, num=1):
        """Get device that already exists by location."""
        return self.get_device(None, None, location, num)

    def get_device(self, t, feature, location, num=1):
        """Get a new device by feature and location."""
        assert num == 1, "We don't support getting more than one device currently!"

        matching = self.devices[:]
        if t is not None:
            matching[:] = [d for d in matching if d.type == t]
        if feature is not None:
            matching[:] = [d for d in matching if feature in d.features]
        if location is not None:
            matching[:] = [d for d in matching if d.location == location]

        if len(matching) > 1:
            logger.debug(
                f"multiple matches, returning first hit ({t}, {feature}, {location})"
            )
            for m in matching:
                logger.debug(m)

        if len(matching) == 0:
            return DeviceNone()

        return matching[0].obj

    def _add_device(self, dev, override=False, plugin=False):
        """To add devices created via old method get_device()."""
        new_dev = device_descriptor()
        if plugin:
            # first check if dev.name exist
            if not hasattr(device_type, dev.name):
                extend_enum(device_type, dev.name, self.plugin_counter)
                self.plugin_counter -= 1
            else:
                logger.warning(
                    "WARNING!! WARNING!! this device cannot be added as a plugin"
                    "\nCode will fail, if two devices found with same name."
                )
        if len(self.devices) == 0:
            new_dev.type = device_type.DUT
        else:
            new_dev.type = getattr(device_type, dev.name, device_type.Unknown)
        new_dev.obj = dev
        self.devices.append(new_dev)

        array_name = getattr(dev, "dev_array", None)
        if array_name:
            self.set_device_array(array_name, dev, override)
        if getattr(dev, "legacy_add", True):
            # For convenience, set an attribute with a name the same as the
            # newly added device type. Example: self.lan = the device of type lan
            attribute_name = new_dev.type.name
            if (
                attribute_name != "Unknown"
                and getattr(self, attribute_name, None) is not None
            ):
                # device manager already has an attribute of this name
                raise Exception(
                    "Device Manager already has '%s' attribute, you cannot add another."
                    % attribute_name
                )
            setattr(self, attribute_name, new_dev.obj)
            # Alias board to DUT
            if attribute_name == "DUT":
                self.board = new_dev.obj


def clean_device_manager():
    """This will remove the instance reference maintained by singleton wrapper"""
    # this will be dynamically populated by singleton.
    # Need to ignore the pylint error.
    instances: Dict = device_manager.__closure__[  # pylint: disable=maybe-no-member
        1
    ].cell_contents
    while instances:
        instances.popitem()
