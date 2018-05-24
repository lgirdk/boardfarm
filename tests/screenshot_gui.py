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
        display = Display(visible=0, size=(1366, 768))
        display.start()

        try:
            if 'http_proxy' in lan.config:
                proxy = lan.config['http_proxy']
            else:
                ip = lan.config['ipaddr']
                lan.sendline('cat /proc/net/vlan/config')
                lan.expect('eth1.*\|\s([0-9]+).*\|')
                port = 8000 + int(lan.match.group(1))
                lan.expect(prompt)
                proxy = "%s:%s" % (ip, port)
        except:
            raise Exception("No reasonable http proxy found, please add one to the board config")

        print("Using proxy %s" % proxy)
        driver = lib.common.firefox_webproxy_driver(proxy)
        driver.maximize_window()
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
