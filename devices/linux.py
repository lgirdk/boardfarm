# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import pexpect

def enable_ipv6(device, interface):
    device.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=0")
    device.expect(device.prompt, timeout=60)

def disable_ipv6(device, interface):
    device.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=1")
    device.expect(device.prompt, timeout=60)
