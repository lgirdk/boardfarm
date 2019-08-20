# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import rootfs_boot
from boardfarm import lib
from boardfarm.devices import board, wan, lan, prompt

from pyvirtualdisplay import Display
import pexpect
import os

class RunBrowserViaProxy(rootfs_boot.RootFSBootTest):
    '''Bootstrap firefox running via localproxy'''
    def start_browser(self):
        try:
            x,y=self.config.get_display_backend_size()
            # try to start vnc server
            self.display = Display(backend=self.config.default_display_backend,
                                   rfbport=self.config.default_display_backend_port,
                                   visible=0,
                                   size=(x, y))
            self.display.start()

            if "BFT_DEBUG" in os.environ:
                print("Connect to VNC display running on localhost:"+self.config.default_display_backend_port)
                raw_input("Press any key after connecting to display....")
        except:
            # fallback xvfb
            self.display = Display(visible=0, size=(1366, 768))
            self.display.start()

        try:
            if lan.http_proxy is not None:
                proxy = lan.http_proxy
            elif lan.ipaddr is not None:
                ip = lan.ipaddr
                lan.sendline('cat /proc/net/vlan/config')
                lan.expect('%s.*\|\s([0-9]+).*\|' % lan.iface_dut)
                port = 8000 + int(lan.match.group(1))
                lan.expect(prompt)
                proxy = "%s:%s" % (ip, port)
            else:
                # no proxy, use message below
                assert False
        except Exception as e:
            print(e)
            raise Exception("No reasonable http proxy found, please add one to the board config")

        board.enable_mgmt_gui(board, wan)

        print("Using proxy %s" % proxy)
        driver = lib.common.get_webproxy_driver(proxy, self.config)

        return driver

    def runTest(self):
        driver = self.start_browser()

        print("Browser is running, connect and debug")
        print("Press Control-] to exit interactive mode")
        board.interact()

        self.recover()

    def recover(self):
        try:
            self.display.stop()
        except:
            pass
        try:
            self.display.sendstop()
        except:
            pass
        try:
            self.display.popen.kill()
        except:
            pass

class ScreenshotGUI(RunBrowserViaProxy):
    '''Starts Firefox via a proxy to the LAN and takes a screenshot'''
    def runTest(self):
        driver = self.start_browser()

        print("taking ss of http://%s" % board.lan_gateway)
        driver.get("http://%s" % board.lan_gateway)

        # wait for possible redirects to settle down
        url = driver.current_url
        for i in range(10):
            board.expect(pexpect.TIMEOUT, timeout=5)
            if url == driver.current_url:
                break
            url = driver.current_url
        board.expect(pexpect.TIMEOUT, timeout=10)

        # take screenshot
        driver.save_screenshot(self.config.output_dir + os.sep + 'lan_portal.png')

        driver.close()

        self.recover()
