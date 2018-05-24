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

class ScreenshotGUI(rootfs_boot.RootFSBootTest):
    '''Starts Firefox via a proxy to the LAN and takes a screenshot'''
    def runTest(self):

        display = Display(visible=0, size=(1366, 768))
        display.start()

        #lan_ip = lan.get_interface_ipaddr('eth1')
        #lan_proxy_port = TODO
        # TODO: find proxy port dynamically
        # NOTE: we start a web proxy on all lan devices automatically (tinyproxy)

        driver = lib.common.firefox_webproxy_driver("localhost:8080")

        driver.maximize_window()
        print ("taking ss of http://%s" % board.lan_gateway)
        driver.get("http://%s" % board.lan_gateway)
        driver.save_screenshot('lan_portal.png')

        driver.close()
