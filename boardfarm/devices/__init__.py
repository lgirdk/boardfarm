'''

    This directory contains classes for connecting to and controlling
    devices over a network.

'''
import os
import sys
import glob
import inspect
import pexpect
import termcolor

# insert tests lib so devices and tests can share the same libraries
sys.path.insert(0, os.path.dirname(__file__) + '/../tests')
sys.path.insert(0, os.path.dirname(__file__))

board = None
lan = None
wan = None
wlan = None
wlan2g = None
wlan5g = None
prompt = None

device_files = glob.glob(os.path.dirname(__file__)+"/*.py")
device_files += [e.replace('/__init__', '') for e in glob.glob(os.path.dirname(__file__) + '/*/__init__.py')]
if 'BFT_OVERLAY' in os.environ:
    for overlay in os.environ['BFT_OVERLAY'].split(' '):
        overlay = os.path.realpath(overlay)
        sys.path.insert(0, overlay + '/devices')
        device_files += glob.glob(overlay + '/devices/*.py')
        device_files += [e.replace('/__init__', '') for e in glob.glob(overlay + '/devices/*/__init__.py')]

        sys.path.insert(0, overlay + '/tests')

    sys.path.insert(0, os.getcwd() + '/devices')

device_mappings = { }
for x in sorted([os.path.basename(f)[:-3] for f in device_files if not "__" in f]):
    exec("import %s as device_file" % x)
    device_mappings[device_file] = []
    for obj in dir(device_file):
        ref = getattr(device_file, obj)
        if inspect.isclass(ref) and hasattr(ref, "model"):
            device_mappings[device_file].append(ref)
            exec("from %s import %s" % (x, obj))

def check_for_cmd_on_host(cmd, msg=None):
    '''Prints an error message with a suggestion on how to install the command'''
    from lib.common import cmd_exists
    if not cmd_exists(cmd):
        termcolor.cprint("\nThe  command '"+cmd+"' is NOT installed on your system. Please install it.", None, attrs=['bold'])
        if msg is not None: print(cmd+": "+msg)
        import sys
        if sys.platform == "linux2":
            import platform
            if "Ubuntu" in platform.dist() or "debian" in platform.dist():
                print("To install run:\n\tsudo apt install <package with "+cmd+">")
                exit(1)
        print("To install refer to your system SW app installation instructions")

def initialize_devices(configuration):
    # Init random global variables. To Do: clean these.
    global power_ip, power_outlet
    conn_cmd = configuration.board.get('conn_cmd')
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
                attr not in ('model','prompt')]
        common = list(set(members) & set(cls_members))
        if len(common) > 0:
            raise Exception("Identified duplicate class members %s between classes  %s" % (str(common), str(cls_list[:cls_list.index(cls)+1])))

        cls_members.extend(members)
        temp.append(cls)

    cls_list = temp
    cls_name = "_".join([cls.__name__ for  cls in cls_list])

    def __init__(self, *args, **kwargs):
        for cls in cls_list:
            cls.__init__(self, *args, **kwargs)

    return type(cls_name, tuple(cls_list), {'__init__':__init__})(model,**kwargs)

def get_device(model, **kwargs):
    profile = kwargs.get("profile", {})
    cls_list = []
    for device_file, devs in device_mappings.iteritems():
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
                        profile_kwargs = profile[ list(set(attr) & set(profile))[0] ]

                if profile_exists:
                    if dev not in cls_list: 
                        cls_list.append(dev)
                    else:
                        print("Skipping duplicate device type: %s" % attr)
                        continue
                    common_keys = set(kwargs) & set(profile_kwargs)
                    if len(common_keys) > 0:
                        print("Identified duplicate keys in profile and base device : %s" % str(list(common_keys)) )
                        print("Removing duplicate keys from profile!")
                        for i in list(common_keys):
                            profile_kwargs.pop(i)
                    kwargs.update(profile_kwargs)

    try:
        if len(cls_list) == 0: 
            raise Exception("Unable to spawn instance of model: %s" % model)
        return bf_node(cls_list, model, **kwargs)
    except pexpect.EOF:
        msg = "Failed to connect to a %s, unable to connect (in use) or possibly misconfigured" % model
        raise Exception(msg)
    except Exception as e:
        raise Exception(str(e))

    return None

def board_decider(model, **kwargs):
    if any('conn_cmd' in s for s in kwargs):
        if any(u'kermit' in s for s in kwargs['conn_cmd']):
            check_for_cmd_on_host('kermit',"telnet equivalent command. It has lower CPU usage than telnet,\n\
and works exactly the same way (e.g. kermit -J <ipaddr> [<port>])\n\
You are seeing this message as your configuration is now using kermit instead of telnet.")

    dynamic_dev = get_device(model, **kwargs)
    if dynamic_dev is not None:
        return dynamic_dev

    # Default for all other models
    print("\nWARNING: Unknown board model '%s'." % model)
    print("Please check spelling, your environment setup, or write an appropriate class "
          "to handle that kind of board.")

    if 'BFT_OVERLAY' in os.environ:
        print("\nIs this correct? BFT_OVERLAY=%s\n" % os.environ['BFT_OVERLAY'])
    else:
        print("No BFT_OVERLAY is set, do you need one?")

    if 'BFT_CONFIG' in os.environ:
        print("\nIs this correct? BFT_CONFIG=%s\n" % os.environ['BFT_CONFIG'])
    else:
        print("No BFT_CONFIG is set, do you need one?")

    return openwrt_router.OpenWrtRouter(model, **kwargs)
