"""Interact with console, wan, lan, wlan connections and re-run tests."""
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import logging
import sys

from termcolor import colored

from boardfarm import lib, tests
from boardfarm.tests import rootfs_boot

logger = logging.getLogger("bft")


class Interact(rootfs_boot.RootFSBootTest):
    """Interact with console, wan, lan, wlan connections and re-run tests."""

    def print_dynamic_devices(self):
        """Print dynamic devices."""
        for device in self.config.devices:
            d = getattr(self.config, device)
            # TODO: should move all classes to use string repr
            if hasattr(d, "username"):
                print(f"  {device} device:    ssh {d.username}@{d.name}")
            else:
                print(f"  {d.name} device:    {d}")

    def test_main(self):
        """Function to interact menu."""
        if "pytest" in sys.modules:
            logger.warning(
                colored(
                    f"DEPRECATION WARNING: use pytest interact to have test discovery and fixture invocation",
                    color="red",
                    attrs=["bold"],
                )
            )

        board = self.dev.board
        lib.common.test_msg("Press Ctrl-] to stop interaction and return to menu")
        board.sendline()
        try:
            board.interact()
        except Exception as error:
            print(error)
            return

        while True:
            print("\n\nCurrent station")
            print(f"  Board console: {self.config.board.get('conn_cmd')}")
            self.print_dynamic_devices()
            print(
                "Pro-tip: Increase kernel message verbosity with\n"
                '    echo "7 7 7 7" > /proc/sys/kernel/printk'
            )
            print("Menu")
            i = 2
            if board.consoles is None:
                print("  1: Enter console")
                i += 1
            else:
                i = 1
                for c in board.consoles:
                    print(f"  {i}: Enter console")
                    i += 1

            print(f"  {i}: List all tests")
            i += 1
            print(f"  {i}: Run test")
            i += 1
            print(f"  {i}: Reset board")
            i += 1
            print(f"  {i}: Enter interactive python shell")
            i += 1
            if len(self.config.devices) > 0:
                print(f"  Type a device name to connect: {self.config.devices}")
            print("  x: Exit")
            key = input("Please select: ")

            if key in self.config.devices:
                d = getattr(self.config, key)
                d.interact()

            i = 1
            for c in board.consoles:
                if key == str(i):
                    c.interact()
                i += 1

            if key == str(i):
                try:
                    tests.init(self.config)
                except Exception as e:
                    print("Unable to re-import tests!")
                    print(e)
                else:
                    print("Available tests:")
                    print("\n".join(tests.available_tests.keys()))
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

                    try:
                        tests.available_tests[test](
                            self.config, self.dev, self.env_helper
                        ).run()
                    except Exception as e:
                        lib.common.test_msg(
                            "Failed to find and/or run test, continuing.."
                        )
                        print(e)
                        continue
                    finally:
                        func = getattr(
                            tests.available_tests[test].__class__,
                            "teardown_class",
                            None,
                        )
                        if func:
                            try:
                                tests.available_tests[test].teardown_wrapper(func)
                            except Exception as e:
                                print(e)
                                print(
                                    "This should never happen. TearDown should be fail-safe"
                                )

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
                    import readline  # optional, will allow Up/Down/History in the console

                    assert readline  # silence pyflakes
                    import code

                    vars = globals().copy()
                    vars.update(locals())
                    shell = code.InteractiveConsole(vars)
                    shell.interact()
                except Exception as error:
                    print(error)
                    print("Unable to spawn interactive shell!")
                continue
            i += 1

            if key == "x":
                break
