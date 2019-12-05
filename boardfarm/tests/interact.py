# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.tests import rootfs_boot
from boardfarm import tests
from boardfarm import lib
import sys
from boardfarm.devices import board, wan, lan, wlan, prompt

class Interact(rootfs_boot.RootFSBootTest):
    '''Interact with console, wan, lan, wlan connections and re-run tests'''

    def print_legacy_devices(self):
        print("  LAN device:    ssh %s@%s" % (self.config.board.get('lan_username', "root"), self.config.board.get('lan_device')))
        print("  WAN device:    ssh %s@%s" % (self.config.board.get('wan_username', "root") ,self.config.board.get('wan_device')))

    def print_dynamic_devices(self):
        for device in self.config.devices:
            d = getattr(self.config, device)
            # TODO: should move all classes to use string repr
            if hasattr(d, 'username'):
                print("  %s device:    ssh %s@%s" % (device, d.username, d.name))
            else:
                print("  %s device:    %s" % (d.name, d))

    def runTest(self):
        legacy = hasattr(self.config, "wan_device")
        lib.common.test_msg("Press Ctrl-] to stop interaction and return to menu")
        board.sendline()
        try:
            board.interact()
        except:
            return

        while True:
            print("\n\nCurrent station")
            print("  Board console: %s" % self.config.board.get('conn_cmd'))
            if legacy:
                self.print_legacy_devices()
            self.print_dynamic_devices()
            print('Pro-tip: Increase kernel message verbosity with\n'
                  '    echo "7 7 7 7" > /proc/sys/kernel/printk')
            print("Menu")
            i = 2
            if board.consoles is None:
                print("  1: Enter console")
                i += 1
            else:
                i = 1
                for c in board.consoles:
                    print("  %s: Enter console" % i)
                    i += 1
            if legacy: 
                print("  %s: Enter wan console" % i)
                i += 1
                print("  %s: Enter lan console" % i)
                i += 1
                print("  %s: Enter wlan console" % i)
                i += 1

            print("  %s: List all tests" % i)
            i += 1
            print("  %s: Run test" % i)
            i += 1
            print("  %s: Reset board" % i)
            i += 1
            print("  %s: Enter interactive python shell" % i)
            i += 1
            if len(self.config.devices) > 0:
                print("  Type a device name to connect: %s" % self.config.devices)
            print("  x: Exit")
            key = raw_input("Please select: ")

            if key in self.config.devices:
                d = getattr(self.config, key)
                d.interact()

            i = 1
            for c in board.consoles:
                if key == str(i):
                    c.interact()
                i += 1

            if legacy:
                if key == str(i):
                    wan.interact()
                    continue
                i += 1

                if key == str(i):
                    lan.interact()
                    continue
                i += 1

                if key == str(i):
                    wlan.interact()
                    continue
                i += 1

            if key == str(i):
                try:
                    tests.init(self.config)
                except Exception as e:
                    print("Unable to re-import tests!")
                    print(e)
                else:
                    print("Available tests:")
                    print('\n'.join(tests.available_tests.keys()))
                continue
            i += 1

            if key == str(i):
                try:
                    tests.init(self.config)
                except Exception as e:
                    print("Unable to re-import tests!")
                    print(e)
                else:
                    # TODO: use an index instead of test name
                    print("Type test to run: ")
                    test = sys.stdin.readline().strip()

                    #try:
                    board.sendline()
                    # default are 1 1 1 7
                    board.set_printk()
                    board.expect(prompt)
                    try:
                        tests.available_tests[test](self.config).run()
                    except Exception as e:
                        lib.common.test_msg("Failed to find and/or run test, continuing..")
                        print(e)
                        continue

                continue
            i += 1

            if key == str(i):
                board.reset()
                print("Press Ctrl-] to stop interaction and return to menu")
                board.interact()
                continue
            i += 1

            if key == str(i):
                print("Enter python shell, press Ctrl-D to exit")
                try:
                    from IPython import embed
                    embed()
                except:
                    try:
                        import readline # optional, will allow Up/Down/History in the console
                        assert readline # silence pyflakes
                        import code
                        vars = globals().copy()
                        vars.update(locals())
                        shell = code.InteractiveConsole(vars)
                        shell.interact()
                    except:
                        print("Unable to spawn interactive shell!")
                continue
            i += 1

            if key == "x":
                break
