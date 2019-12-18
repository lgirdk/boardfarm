'''

    This directory contains classes for connecting to and controlling
    devices over a network.

'''
import os
import sys
import glob
import importlib
import inspect
import pexpect
import termcolor
import traceback
from six.moves import UserList
from aenum import Enum

import boardfarm

# TODO: type + name are confusing and need to be sorted out
# This is really to handle legacy types, you really should be requesting device
# by location and/or feature. E.g. wan2/lan2/etc all start to go away from this
# short list
class device_type(Enum):
    Unknown = 0
    DUT = 1
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
    Unknown = 0
    Northbound = 1
    WAN = 1
    Southbound = 2
    LAN = 2
    DUT = 3

class device_os(Enum):
    Unknown = 0
    Linux = 1
    Windows = 2

# to replace linux_boot.LinuxDevice.get_device_by_feature
class device_feature(Enum):
    Unknown = 0
    Generic = 1
    Wifi2G = 2
    Wifi5G = 3

class device_descriptor(object):
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

        assert len(matching), "We don't know how to create devices by name and none exist!"

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

mgr = device_manager()

# TODO: this probably should not the generic device
from . import openwrt_router

from boardfarm.lib import find_subdirs
from boardfarm.exceptions import BftNotSupportedDevice

# To do: delete these path inserts when everything is properly importing from boardfarm
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Placeholders for devices that are created later
board = None
lan = None
lan2 = None
wan = None
wlan = None
wlan2g = None
wlan5g = None
prompt = None
acs_server = None
cmts = None
provisioner = None

from boardfarm import uniqid

env = {"wan_iface": "wan%s" % uniqid[:12],
        "lan_iface": "lan%s" % uniqid[:12],
        "uniq_id": uniqid}

device_mappings = {}

def probe_devices():
    '''
    Dynamically find all devices classes accross all boardfarm projects.
    '''

    all_boardfarm_modules = boardfarm.plugins
    all_boardfarm_modules['boardfarm'] = importlib.import_module('boardfarm')

    # Loop over all modules to import their devices
    for modname in all_boardfarm_modules:
        # Find all python files in 'devices' directories
        location = os.path.join(os.path.dirname(all_boardfarm_modules[modname].__file__), 'devices')
        file_names = glob.glob(os.path.join(location, '*.py'))
        file_names = [os.path.basename(x)[:-3] for x in file_names if not "__" in x]
        # Find sub modules too
        sub_mod = glob.glob(os.path.join(location, '*', '__init__.py'))
        file_names += [os.path.basename(os.path.dirname(x)) for x in sub_mod]
        # Import devices
        for fname in sorted(file_names):
            tmp = '%s.devices.%s' % (modname, fname)
            try:
                module = importlib.import_module(tmp)
            except Exception:
                if 'BFT_DEBUG' in os.environ:
                    traceback.print_exc()
                    print("Warning: could not import from file %s.py" % fname)
                else:
                    print("Warning: could not import from file %s.py. Run with BFT_DEBUG=y for more details" % fname)
                continue
            device_mappings[module] = []
            for thing_name in dir(module):
                thing = getattr(module, thing_name)
                if inspect.isclass(thing) and hasattr(thing, 'model'):
                    device_mappings[module].append(thing)

def check_for_cmd_on_host(cmd, msg=None):
    '''Prints an error message with a suggestion on how to install the command'''
    from boardfarm.lib.common import cmd_exists
    if not cmd_exists(cmd):
        termcolor.cprint("\nThe  command '" + cmd + "' is NOT installed on your system. Please install it.", None, attrs=['bold'])
        if msg is not None: print(cmd + ": " + msg)
        import sys
        if sys.platform == "linux2":
            import platform
            if "Ubuntu" in platform.dist() or "debian" in platform.dist():
                print("To install run:\n\tsudo apt install <package with " + cmd + ">")
                exit(1)
        print("To install refer to your system SW app installation instructions")

def initialize_devices(configuration):
    # Init random global variables. To Do: clean these.
    global power_ip, power_outlet
    power_ip = configuration.board.get('powerip', None)
    power_outlet = configuration.board.get('powerport', None)
    # Init devices
    global board, lan, wan, wlan, wlan2g, wlan5g, prompt
    board = configuration.console
    lan = None
    wan = None
    wlan = None
    wlan2g = None
    wlan5g = None

    for device in configuration.devices:
        globals()[device] = getattr(configuration, device)

    board.root_type = None
    # Next few lines combines all the prompts into one list of unique prompts.
    # It lets test writers use "some_device.expect(prompt)"
    prompt = []
    for d in (board, lan, wan, wlan):
        prompt += getattr(d, "prompt", [])
    prompt = list(set(prompt))

def bf_node(cls_list, model, **kwargs):
    '''
    Method bf_node returns an instance of a dynamically created class.
    The class is created using type(classname, superclasses, attributes_dict) method.
    Parameters:
    cls_list (list): Superclasses for the dynamically created class.
    model (str), **kwargs: used for defining attributes of the dynamic class.
    '''
    cls_name = "_".join([cls.__name__ for cls in cls_list])
    cls_members = []
    '''Need to ensure that profile does not have members which override
    the base_cls implementation.'''
    temp = []
    for cls in cls_list:
        members = [attr for attr in cls.__dict__ if
                not attr.startswith('__') and
                not attr.endswith('__') and
                attr not in ('model', 'prompt')]
        common = list(set(members) & set(cls_members))
        if len(common) > 0:
            raise Exception("Identified duplicate class members %s between classes  %s" % (str(common), str(cls_list[:cls_list.index(cls) + 1])))

        cls_members.extend(members)
        temp.append(cls)

    cls_list = temp
    cls_name = "_".join([cls.__name__ for cls in cls_list])

    def __init__(self, *args, **kwargs):
        for cls in cls_list:
            cls.__init__(self, *args, **kwargs)

    ret = type(cls_name, tuple(cls_list), {'__init__': __init__})(model, **kwargs)
    ret.target = kwargs

    return ret

def get_device(model, **kwargs):
    profile = kwargs.get("profile", {})
    cls_list = []
    profile_list = []
    for device_file, devs in device_mappings.items():
        for dev in devs:
            if 'model' in dev.__dict__:
                attr = dev.__dict__['model']

                if type(attr) is str and model == attr:
                    cls_list.append(dev)
                elif type(attr) is tuple and model in attr:
                    cls_list.append(dev)

                profile_exists = False
                if len(profile) > 0:
                    if type(attr) is str and attr in profile:
                        profile_exists = True
                        profile_kwargs = profile[attr]
                    elif type(attr) is tuple and len(set(attr) & set(profile)) == 1:
                        profile_exists = True
                        profile_kwargs = profile[list(set(attr) & set(profile))[0]]

                if profile_exists:
                    if dev not in cls_list:
                        profile_list.append(dev)
                    else:
                        print("Skipping duplicate device type: %s" % attr)
                        continue
                    common_keys = set(kwargs) & set(profile_kwargs)
                    if len(common_keys) > 0:
                        print("Identified duplicate keys in profile and base device : %s" % str(list(common_keys)))
                        print("Removing duplicate keys from profile!")
                        for i in list(common_keys):
                            profile_kwargs.pop(i)
                    kwargs.update(profile_kwargs)

    try:
        # to ensure profile always initializes after base class.
        cls_list.extend(profile_list)
        if len(cls_list) == 0:
            raise BftNotSupportedDevice("Unable to spawn instance of model: %s" % model)
        ret = bf_node(cls_list, model, **kwargs)
        mgr._add_device(ret)
        return ret
    except BftNotSupportedDevice:
        raise
    except pexpect.EOF:
        msg = "Failed to connect to a %s, unable to connect (in use) or possibly misconfigured" % model
        raise Exception(msg)
    except Exception as e:
        traceback.print_exc()
        raise Exception(str(e))

    return None

def board_decider(model, **kwargs):
    if any('conn_cmd' in s for s in kwargs):
        if any(u'kermit' in s for s in kwargs['conn_cmd']):
            check_for_cmd_on_host('kermit', "telnet equivalent command. It has lower CPU usage than telnet,\n\
and works exactly the same way (e.g. kermit -J <ipaddr> [<port>])\n\
You are seeing this message as your configuration is now using kermit instead of telnet.")

    dynamic_dev = get_device(model, **kwargs)
    if dynamic_dev is not None:
        return dynamic_dev

    # Default for all other models
    print("\nWARNING: Unknown board model '%s'." % model)
    print("Please check spelling, your environment setup, or write an appropriate class "
          "to handle that kind of board.")

    if len(boardfarm.plugins) > 0:
        print("The following boardfarm plugins are installed.")
        print("Do you need to update them or install others?")
        print("\n".join(boardfarm.plugins))
    else:
        print("No boardfarm plugins are installed, do you need to install some?")

    if 'BFT_CONFIG' in os.environ:
        print("\nIs this correct? BFT_CONFIG=%s\n" % os.environ['BFT_CONFIG'])
    else:
        print("No BFT_CONFIG is set, do you need one?")

    return openwrt_router.OpenWrtRouter(model, **kwargs)
