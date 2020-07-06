# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import ipaddress

from . import qemu


class QemuOpenWrt(qemu.Qemu):
    """Emulated QEMU board."""

    model = "qemux86-openwrt"

    wan_iface = "eth1"
    lan_iface = "br-lan"

    lan_network = ipaddress.IPv4Network(u"192.168.1.0/24")
    lan_gateway = ipaddress.IPv4Address(u"192.168.1.1")
