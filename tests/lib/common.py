# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import json
import pexpect
import sys
import subprocess
import time
import unittest2
import urllib2
import os
import signal
import config
from termcolor import cprint

from selenium import webdriver
from selenium.webdriver.common.proxy import *

ubootprompt = ['ath>', '\(IPQ\) #', 'ar7240>']
linuxprompt = ['root\\@.*:.*#', '@R7500:/# ']
prompts = ubootprompt + linuxprompt + ['/.* # ', ]

def run_once(f):
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return f(*args, **kwargs)
    wrapper.has_run = False
    return wrapper

def spawn_ssh_pexpect(ip, user='root', pw='bigfoot1', prompt=None, port="22", via=None, color=None, o=sys.stdout):
    if via:
        p = via.sendline("ssh %s@%s -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
                                            % (user, ip, port))
        p = via
    else:
        p = pexpect.spawn("ssh %s@%s -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
                                            % (user, ip, port))

    i = p.expect(["yes/no", "assword:", "Last login"], timeout=30)
    if i == 0:
        p.sendline("yes")
        i = self.expect(["Last login", "assword:"])
    if i == 1:
        p.sendline(pw)
    else:
        pass

    if prompt is None:
        p.prompt = "%s@.*$" % user
    else:
        p.prompt = prompt

    p.expect(p.prompt)

    from termcolor import colored
    class o_helper():
            def __init__(self, color):
                    self.color = color
            def write(self, string):
                    o.write(colored(string, color))
            def flush(self):
                    o.flush()

    if color is not None:
        p.logfile_read = o_helper(color)
    else:
        p.logfile_read = o

    return p

def clear_buffer(console):
    try:
        console.read_nonblocking(size=2000, timeout=1)
    except:
        pass

def phantom_webproxy_driver(ipport):
    '''
    Use this if you started web proxy on a machine connected to router's LAN.
    '''
    service_args = [
        '--proxy=' + ipport,
        '--proxy-type=http',
    ]
    print("Attempting to setup Phantom.js via proxy %s" % ipport)
    driver = webdriver.PhantomJS(service_args=service_args)
    driver.set_window_size(1024, 768)
    driver.set_page_load_timeout(30)
    return driver

def firefox_webproxy_driver(ipport):
    '''
    Use this if you started web proxy on a machine connected to router's LAN.
    '''

    ip, port = ipport.split(':')

    profile = webdriver.FirefoxProfile()
    profile.set_preference("network.proxy.type", 1)
    profile.set_preference("network.proxy.http", ip)
    profile.set_preference("network.proxy.http_port", int(port))
    # missing the ssl proxy, should we add it?
    profile.set_preference("network.proxy.ftp", ip)
    profile.set_preference("network.proxy.ftp_port", int(port))
    profile.set_preference("network.proxy.socks", ip)
    profile.set_preference("network.proxy.socks_port", int(port))
    profile.set_preference("network.proxy.socks_remote_dns", True)
    profile.update_preferences()
    driver = webdriver.Firefox(firefox_profile=profile)
    driver.implicitly_wait(30)
    driver.set_page_load_timeout(30)

    return driver

def chrome_webproxy_driver(ipport):
    '''
    Use this if you prefer Chrome. Should be the same as firefox_webproxy_driver
    above, although ChromeWebDriver seems to be slower in loading pages.
    '''

    chrome_options = webdriver.ChromeOptions()
    if config.default_proxy_type ==  'sock5':
        chrome_options.add_argument("--proxy-server=socks5://" + ipport);
    else:
        chrome_options.add_argument('--proxy-server=' + ipport)

    chrome_options.add_argument("--start-maximized")

    if "BFT_DEBUG" in os.environ:
        print("chrome can be connected to Xvnc")
    else:
        print("chrome running headless")
        chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)

    driver.implicitly_wait(30)
    driver.set_page_load_timeout(30)

    return driver

def get_webproxy_driver(ipport):
    if config.default_web_driver == "ffox":
        d = firefox_webproxy_driver(ipport)
        d.maximize_window()
        return d
    elif config.default_web_driver == "chrome":
        return chrome_webproxy_driver(ipport)
        # the win maximise is done in the chrome options
    else:
        # something has gone wrong, make the error message as self explanatory as possible
        msg = "No usable web_driver specified, please add one to the board config"
        if config.default_web_driver is not None:
            msg = msg + " (value in config: '"+config.default_web_driver+"' not recognised)"
        else:
            # this should never happen
            msg = msg + "(no default value set, please check boardfarm/config.py)"
        raise Exception(msg)

    print("Using proxy %s, webdriver: %s" % (proxy, config.default_web_driver))

def test_msg(msg):
    cprint(msg, None, attrs=['bold'])

class TestResult:
    logged = {}
    def __init__(self, name, grade, message):
        self.name = name
        self.result_grade = grade
        self.result_message = message

cmd_exists = lambda x: any(os.access(os.path.join(path, x), os.X_OK) for path in os.environ["PATH"].split(os.pathsep))
