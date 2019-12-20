import os
from aenum import Enum
from six.moves import UserList

from boardfarm.exceptions import DeviceDoesNotExistError

class DeviceNone(object):
    def __getattr__(self, key):
        raise DeviceDoesNotExistError

# TODO: type + name are confusing and need to be sorted out
# This is really to handle legacy types, you really should be requesting device
# by location and/or feature. E.g. wan2/lan2/etc all start to go away from this
# short list
class device_type(Enum):
    '''
    Identifiers for different kinds of devices. Useful for correctly
    connecting to and using a device.
    '''
    Unknown = 0
    DUT = 1
    board = 1
    wan = 2
    wan2 = 2
    lan = 3
    lan2 = 3
    sipcenter = 4
    acs_server = 5
    wifi = 6
    gre = 7
    provisioner = 8
    syslog_server = 9
    ixia1 = 10
    wan_factory = 11
    lan_factory = 11
    fax_modem = 12
    fax_modem1 = 12
    fax_modem2 = 12
    wlan = 13
    wlan2 = 13
    cmts = 14
    cdrouter = 15

class device_location(Enum):
    '''
    Identifiers for how a device is connected to the Device Under Test (DUT).
    '''
    Unknown = 0
    Northbound = 1
    WAN = 1
    Southbound = 2
    LAN = 2
    DUT = 3

class device_os(Enum):
    '''
    Identifiers for the type of Operating System (OS) of a device.
    '''
    Unknown = 0
    Linux = 1
    Windows = 2

# to replace linux_boot.LinuxDevice.get_device_by_feature
class device_feature(Enum):
    '''
    Identifiers for extra features a device may have.
    '''
    Unknown = 0
    Generic = 1
    Wifi2G = 2
    Wifi5G = 3

class device_descriptor(object):
    '''
    All identifiers about a device.
    '''
    location = device_location.Unknown
    os = device_os.Linux
    type = device_type.Unknown
    features = [device_feature.Unknown]
    obj = None

class device_manager(UserList):
    '''
    Manages all your devices, for getting and creating (if needed)
    '''

    '''
    List of current devices, which we prefer to reuse instead of creating new ones
    '''
    devices = []

    data = property(lambda self: [ x.obj for x in self.devices ] , lambda *args: None)

    '''
    Devices that can create other devices, we store them for later
    so we can use them to create devices that might not already exist
    '''
    factories = []

    def by_type(self, t, num=1):
        '''Shorthand for getting device by type'''
        return self.get_device_by_type(t, num)

    def by_types(self, types):
        '''Shorthand for getting devices by types'''
        return self.get_devices_by_types(types)

    def get_device_by_type(self, t, num=1):
        '''Get device that already exists by type'''
        return self.get_device(t, None, None, num)

    def get_devices_by_types(self, types):
        '''Get multiple devices by types'''

        return [ self.by_type(t, num=1) for t in types ]

    def by_feature(self, feature, num=1):
        '''Shorthand for getting device by feature'''
        return self.get_device_by_feature(feature, num)

    def get_device_by_feature(self, feature, num=1):
        '''Get device that already exists by feature'''
        return self.get_device(None, feature, None, num)

    def by_location(self, location, num=1):
        '''Shorthand for getting device by location'''
        return self.get_device_by_location(location, num)

    def get_device_by_location(self, location, num=1):
        '''Get device that already exists by location'''
        return self.get_device(None, None, location, num)

    def get_device(self, t, feature, location, num=1):
        '''Get's a new device by feature and location'''
        assert num == 1, "We don't support getting more than one device currently!"

        matching = self.devices[:]
        if t is not None:
            matching[:] = [ d for d in matching if d.type == t ]
        if feature is not None:
            matching[:] = [ d for d in matching if feature in d.features ]
        if location is not None:
            matching[:] = [ d for d in matching if d.location == location ]

        if len(matching) > 1 and 'BFT_DEBUG' in os.environ:
            print("multiple matches, returning first hit")

        if len(matching) == 0:
            return DeviceNone()

        return matching[0].obj

    def _add_device(self, dev):
        '''Hook to add devices created via old method get_device()'''

        new_dev = device_descriptor()
        if len(self.devices) == 0:
            new_dev.type = device_type.DUT
        else:
            new_dev.type = getattr(device_type, dev.name, device_type.Unknown)
        new_dev.obj = dev
        self.devices.append(new_dev)
