# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import rootfs_boot
import lib
from devices import board, wan, lan, prompt

from pyvirtualdisplay import Display
import pexpect
import os

class ScreenshotGUI(rootfs_boot.RootFSBootTest):
    '''Starts Firefox via a proxy to the LAN and takes a screenshot'''
    def runTest(self):
        try:
            # try to start vnc server
            self.display = Display(backend='xvnc', rfbport='5904', visible=0, size=(1366, 768))
            self.display.start()

            if "BFT_DEBUG" in os.environ:
                print("Connect to VNC display running on localhost:5904")
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
                lan.expect('eth1.*\|\s([0-9]+).*\|')
                port = 8000 + int(lan.match.group(1))
                lan.expect(prompt)
                proxy = "%s:%s" % (ip, port)
            else:
                # no proxy, use message below
                assert False
        except Exception as e:
            print e
            raise Exception("No reasonable http proxy found, please add one to the board config")

        print("Using proxy %s" % proxy)
        #print("Using FirefoxDriver")
        #driver = lib.common.firefox_webproxy_driver(proxy)
        #driver.maximize_window()
        print("Using ChromeDriver")
        driver = lib.common.chrome_webproxy_driver(proxy)
        print ("taking ss of http://%s" % board.lan_gateway)
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

    def recover(self):
        self.display.stop()
