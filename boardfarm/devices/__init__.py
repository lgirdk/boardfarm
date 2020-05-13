'''

    This directory contains classes for connecting to and controlling
    devices over a network.

'''
import glob
import importlib
import inspect
import os
import sys
import traceback
import types

import boardfarm
import pexpect
import termcolor
from boardfarm.exceptions import BftNotSupportedDevice, ConnectionRefused
from boardfarm.lib.DeviceManager import \
    device_type  # pylint: disable=unused-import
from boardfarm.lib.DeviceManager import all_device_managers
from six.moves import UserList

# TODO: this probably should not the generic device
from . import openwrt_router

device_mappings = {}


def probe_devices():
    '''
    Dynamically find all devices classes accross all boardfarm projects.
    '''

    all_boardfarm_modules = boardfarm.plugins
    all_boardfarm_modules['boardfarm'] = importlib.import_module('boardfarm')

    all_mods = []

    # Loop over all modules to import their devices
    for modname in all_boardfarm_modules:
        # Find all python files in 'devices' directories
        location = os.path.join(
            os.path.dirname(all_boardfarm_modules[modname].__file__),
            'devices')
        file_names = glob.glob(os.path.join(location, '*.py'))
        file_names = [
            os.path.basename(x)[:-3] for x in file_names if not "__" in x
        ]
        # Find sub modules too
        sub_mod = glob.glob(os.path.join(location, '*', '__init__.py'))
        file_names += [os.path.basename(os.path.dirname(x)) for x in sub_mod]
        # Import devices
        for fname in sorted(file_names):
            tmp = '%s.devices.%s' % (modname, fname)
            try:
                module = importlib.import_module(tmp)
                all_mods += [module]
            except Exception:
                if 'BFT_DEBUG' in os.environ:
                    traceback.print_exc()
                    print("Warning: could not import from file %s.py" % fname)
                else:
                    print(
                        "Warning: could not import from file %s.py. Run with BFT_DEBUG=y for more details"
                        % fname)
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
        termcolor.cprint(
            "\nThe  command '" + cmd +
            "' is NOT installed on your system. Please install it.",
            None,
            attrs=['bold'])
        if msg is not None: print(cmd + ": " + msg)
        import sys
        if sys.platform == "linux2":
            import platform
            if "Ubuntu" in platform.dist() or "debian" in platform.dist():
                print("To install run:\n\tsudo apt install <package with " +
                      cmd + ">")
                exit(1)
        print(
            "To install refer to your system SW app installation instructions")


__loader__ = None
_mod = sys.modules[__name__]


class _prompt(UserList, list):
    '''
    This used to be a static list, but since we track devices more closely we can
    now dynamically create this list of prompts. It checks all currently instanstiated
    devices and returns a read-only list
    '''
    def get_prompts(self):
        ret = []

        for dm in all_device_managers:
            for d in dm:
                for p in getattr(d, 'prompt', []):
                    if p not in ret:
                        ret.append(p)

        return ret

    data = property(get_prompts, lambda *args: None)


prompt = _prompt()


def bf_node(cls_list, model, device_mgr, **kwargs):
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
        members = [
            attr for attr in cls.__dict__ if not attr.startswith('__')
            and not attr.endswith('__') and attr not in ('model', 'prompt')
        ]
        common = list(set(members) & set(cls_members))
        if len(common) > 0:
            raise Exception(
                "Identified duplicate class members %s between classes  %s" %
                (str(common), str(cls_list[:cls_list.index(cls) + 1])))

        cls_members.extend(members)
        temp.append(cls)

    cls_list = temp
    cls_name = "_".join([cls.__name__ for cls in cls_list])

    def __init__(self, *args, **kwargs):
        for cls in cls_list:
            cls.__init__(self, *args, **kwargs)

    ret = type(cls_name, tuple(cls_list),
               {'__init__': __init__})(model, mgr=device_mgr, **kwargs)
    ret.target = kwargs

    return ret


def get_device(model, device_mgr, **kwargs):
    '''
    Create a class instance for a device. These are connected to the
    Device Under Test (DUT) board.
    '''
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
                    elif type(attr) is tuple and len(set(attr)
                                                     & set(profile)) == 1:
                        profile_exists = True
                        profile_kwargs = profile[list(
                            set(attr) & set(profile))[0]]

                if profile_exists:
                    if dev not in cls_list:
                        profile_list.append(dev)
                    else:
                        print("Skipping duplicate device type: %s" % attr)
                        continue
                    common_keys = set(kwargs) & set(profile_kwargs)
                    if len(common_keys) > 0:
                        print(
                            "Identified duplicate keys in profile and base device : %s"
                            % str(list(common_keys)))
                        print("Removing duplicate keys from profile!")
                        for i in list(common_keys):
                            profile_kwargs.pop(i)
                    kwargs.update(profile_kwargs)

    try:
        # to ensure profile always initializes after base class.
        cls_list.extend(profile_list)
        if len(cls_list) == 0:
            raise BftNotSupportedDevice(
                "Unable to spawn instance of model: %s" % model)
        ret = bf_node(cls_list, model, device_mgr, **kwargs)
        device_mgr._add_device(ret)
        return ret
    except BftNotSupportedDevice:
        raise
    except ConnectionRefused:
        raise
    except pexpect.EOF:
        msg = "Failed to connect to a %s, unable to connect (in use) or possibly misconfigured" % model
        raise Exception(msg)
    except Exception as e:
        traceback.print_exc()
        raise Exception(str(e))

    return None


def board_decider(model, **kwargs):
    '''
    Create a class instance for the Device Under Test (DUT) board.
    '''
    if any('conn_cmd' in s for s in kwargs):
        if any(u'kermit' in s for s in kwargs['conn_cmd']):
            check_for_cmd_on_host(
                'kermit',
                "telnet equivalent command. It has lower CPU usage than telnet,\n\
and works exactly the same way (e.g. kermit -J <ipaddr> [<port>])\n\
You are seeing this message as your configuration is now using kermit instead of telnet."
            )

    dynamic_dev = get_device(model, **kwargs)
    if dynamic_dev is not None:
        return dynamic_dev

    # Default for all other models
    print("\nWARNING: Unknown board model '%s'." % model)
    print(
        "Please check spelling, your environment setup, or write an appropriate class "
        "to handle that kind of board.")

    if len(boardfarm.plugins) > 0:
        print("The following boardfarm plugins are installed.")
        print("Do you need to update them or install others?")
        print("\n".join(boardfarm.plugins))
    else:
        print(
            "No boardfarm plugins are installed, do you need to install some?")

    if 'BFT_CONFIG' in os.environ:
        print("\nIs this correct? BFT_CONFIG=%s\n" % os.environ['BFT_CONFIG'])
    else:
        print("No BFT_CONFIG is set, do you need one?")

    return openwrt_router.OpenWrtRouter(model, **kwargs)
