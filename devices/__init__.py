'''

    This directory contains classes for connecting to and controlling
    devices over a network.

'''
import os
import sys
import glob
import inspect

board = None
lan = None
wan = None
wlan = None
wlan2g = None
wlan5g = None
prompt = None

device_files = glob.glob(os.path.dirname(__file__)+"/*.py")
if 'BFT_OVERLAY' in os.environ:
    for overlay in os.environ['BFT_OVERLAY'].split(' '):
        overlay = os.path.abspath(overlay)
        sys.path.insert(0, overlay + '/devices')
        device_files += glob.glob(overlay + '/devices/*.py')

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

def get_device(model, **kwargs):
    for device_file, devs in device_mappings.iteritems():
        for dev in devs:
            if 'model' in dev.__dict__:

                attr = dev.__dict__['model']

                if type(attr) is str and model != attr:
                    continue
                elif type(attr) is tuple and model not in attr:
                    continue

                try:
                    return dev(model, **kwargs)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    raise
                except:
                    msg = "Failed to create a %s, unable to connect (in use) or possibly misconfigured" % model
                    raise Exception(msg)

    return None

def board_decider(model, **kwargs):
    dynamic_dev = get_device(model, **kwargs)
    if dynamic_dev is not None:
        return dynamic_dev

    # Default for all other models
    print("\nWARNING: Unknown board model '%s'." % model)
    print("Please check spelling, or write an appropriate class "
          "to handle that kind of board.")
    return openwrt_router.OpenWrtRouter(model, **kwargs)
