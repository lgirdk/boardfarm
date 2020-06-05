# Setup logging
import logging
import os
import sys
import uuid

from aenum import Enum
from boardfarm.exceptions import DeviceDoesNotExistError
from six.moves import UserList

logging.basicConfig(stream=sys.stdout, format="%(message)s")
logger = logging.getLogger("DeviceManager")
logger.setLevel(logging.INFO)  # DEBUG, INFO, WARNING, ERROR, CRITICAL


class DeviceNone(object):
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


class device_array_type(Enum):
    """Identifiers for device array type."""
    wan_clients = 1
    lan_clients = 2


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


class device_descriptor(object):
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


all_device_managers = []


class device_manager(UserList):
    """Manages all your devices, for getting and creating (if needed)."""
    def __init__(self):
        """Instance initialisation."""
        super().__init__()
        # List of current devices, which we prefer to reuse instead of creating new ones
        self.devices = []
        # Devices that can create other devices, we store them for later
        # so we can use them to create devices that might not already exist
        self.factories = []

        # TODO: does self.env really belong here or in device class?
        self.uniqid = uuid.uuid4(
        ).hex[:15]  # Random, unique ID and use first 15 bytes
        self.env = {
            "wan_iface": "wan%s" % self.uniqid[:12],
            "lan_iface": "lan%s" % self.uniqid[:12],
            "uniq_id": self.uniqid,
        }

        all_device_managers.append(self)

    @property
    def data(self):
        return [x.obj for x in self.devices]

    @data.setter
    def data(self, x):
        """To clear/initialize the list of devices."""
        self.devices = x

    def set_device_array(self, array_name, dev, override):
        """Set Device Array details."""
        if getattr(device_array_type, array_name, None):
            dev_array = getattr(self, array_name, [])
            for i in dev_array:
                if i.ipaddr == dev.ipaddr:
                    if i.port == dev.port:
                        if not override:
                            raise Exception(
                                "Device manager already had a device with same port and ip details."
                            )
            dev_array.append(dev)
            setattr(self, array_name, dev_array)
        else:
            raise Exception("Invalid device array type %s" % array_name)

    def close_all(self):
        """Close connections to all devices."""
        for d in self.devices:
            try:
                logger.debug("Closing connection to '%s'." % d.type.name)
                d.obj.close()
            except Exception as e:
                logger.warning(e)
                logger.warning("Problem trying to close connection to '%s'." %
                               d.type.name)
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

        if len(matching) > 1 and "BFT_DEBUG" in os.environ:
            print("multiple matches, returning first hit (%s, %s, %s)" %
                  (t, feature, location))
            for m in matching:
                print(m)

        if len(matching) == 0:
            return DeviceNone()

        return matching[0].obj

    def _add_device(self, dev, override=False):
        """To add devices created via old method get_device()."""
        new_dev = device_descriptor()
        if len(self.devices) == 0:
            new_dev.type = device_type.DUT
        else:
            new_dev.type = getattr(device_type, dev.name, device_type.Unknown)
        new_dev.obj = dev
        self.devices.append(new_dev)

        array_name = getattr(dev, "dev_array", None)
        if array_name:
            self.set_device_array(array_name, dev, override)
        if getattr(dev, 'legacy_add', True):
            # For convenience, set an attribute with a name the same as the
            # newly added device type. Example: self.lan = the device of type lan
            attribute_name = new_dev.type.name
            if (attribute_name != "Unknown"
                    and getattr(self, attribute_name, None) is not None):
                # device manager already has an attribute of this name
                raise Exception(
                    "Device Manager already has '%s' attribute, you cannot add another."
                    % attribute_name)
            else:
                setattr(self, attribute_name, new_dev.obj)
                # Alias board to DUT
                if attribute_name == "DUT":
                    setattr(self, "board", new_dev.obj)
