# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os

import pexpect
from pyvirtualdisplay import Display

from boardfarm import lib
from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class RunBrowserViaProxy(rootfs_boot.RootFSBootTest):
    """Bootstrap firefox running via local proxy."""

    def start_browser(self):
        """Try to start vnc server."""
        board = self.dev.board
        wan = self.dev.wan
        lan = self.dev.lan

        try:
            x, y = self.config.get_display_backend_size()
            # try to start vnc server
            self.display = Display(
                backend=self.config.default_display_backend,
                rfbport=self.config.default_display_backend_port,
                visible=0,
                size=(x, y),
            )
            self.display.start()

            if "BFT_DEBUG" in os.environ:
                print(
                    "Connect to VNC display running on localhost:"
                    + self.config.default_display_backend_port
                )
                input("Press any key after connecting to display....")
        except Exception:
            # fallback xvfb
            self.display = Display(visible=0, size=(1366, 768))
            self.display.start()

        try:
            if lan.http_proxy is not None:
                proxy = lan.http_proxy
            elif lan.ipaddr is not None:
                ip = lan.ipaddr
                lan.sendline("cat /proc/net/vlan/config")
                lan.expect(r"%s.*\|\s([0-9]+).*\|" % lan.iface_dut)
                port = 8000 + int(lan.match.group(1))
                lan.expect(prompt)
                proxy = f"{ip}:{port}"
            else:
                # no proxy, use message below
                assert False
        except Exception as e:
            print(e)
            raise Exception(
                "No reasonable http proxy found, please add one to the board config"
            )

        board.enable_mgmt_gui(board, wan)

        print(f"Using proxy {proxy}")
        driver = lib.common.get_webproxy_driver(proxy, self.config)

        return driver

    def runTest(self):
        """Start browser and then connect interactive mode."""
        board = self.dev.board

        self.start_browser()

        print("Browser is running, connect and debug")
        print("Press Control-] to exit interactive mode")
        board.interact()

        self.recover()

    def recover(self):
        """To reset back to initial state."""
        try:
            self.display.stop()
        except Exception:
            pass
        try:
            self.display.sendstop()
        except Exception:
            pass
        try:
            self.display.popen.kill()
        except Exception:
            pass


class ScreenshotGUI(RunBrowserViaProxy):
    """Starts Firefox via a proxy to the LAN and takes a screenshot."""

    def runTest(self):
        """Run browser and take screenshot."""
        board = self.dev.board

        driver = self.start_browser()

        print(f"taking ss of http://{board.lan_gateway}")
        driver.get(f"http://{board.lan_gateway}")

        # wait for possible redirects to settle down
        url = driver.current_url
        for _ in range(10):
            board.expect(pexpect.TIMEOUT, timeout=5)
            if url == driver.current_url:
                break
            url = driver.current_url
        board.expect(pexpect.TIMEOUT, timeout=10)

        # take screenshot
        driver.save_screenshot(self.config.output_dir + os.sep + "lan_portal.png")

        driver.close()

        self.recover()
