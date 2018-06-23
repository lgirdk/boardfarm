# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import re
import rootfs_boot
from devices import board, wan, lan, prompt

import random
import socket
import struct
import ipaddress
from faker import Factory

fake_generator = Factory.create()

class BitTorrentBasic(rootfs_boot.RootFSBootTest):
    '''Super basic simulate of bittorrent traffic'''
    def runTest(self):
        #lan.sendline('apt-get update && apt-get -o Dpkg::Options::="--force-confnew" -y install socat')
        #lan.expect(prompt)

        self.all_ips = []

        # TODO: query interfaces but this is OK for now
        bad_nets = list(ipaddress.ip_network(u"192.168.0.0/24")) + \
                   list(ipaddress.ip_network(u"192.168.1.0/24")) + \
                   list(ipaddress.ip_network(u"10.200.150.0/24"))

        for i in range(1000):
            while True:
                random_ip = fake_generator.ipv4()
                if ipaddress.ip_address(random_ip.decode()) not in bad_nets:
                    if ipaddress.ip_address(random_ip.decode()) not in self.all_ips:
                        break
                else:
                    print ("Skipping ip addr: %s" % random_ip)
            random_port = random.randint(1024, 65535)
            print("Connecting to %s:%s" % (random_ip, random_port))

            self.all_ips.append(random_ip)

            # start listners
            wan.sendline('ip addr add %s/32 dev eth1' % random_ip)
            wan.expect(prompt)

            # this listens on this port on all ips, so we probably want unique ports too
            wan.sendline('nc -w5 -ulp %s > /dev/null &' % random_port)

            args = (random.randint(64, 1073741824), random_ip, random_port)
            lan.sendline('(echo d1:ad2:id20:; head -c %s < /dev/urandom) | nc -u %s %s &' % args)
            lan.expect(prompt)

        lan.sendline('wait', timeout=120)
        lan.expect(prompt)
        self.recover()

    def recover(self):
        for ip in self.all_ips:
            wan.sendline('ip addr del %s/32 dev eth1' % ip)
            wan.expect(prompt)

        wan.sendline('killall nc')
        wan.expect(prompt)
        lan.sendline('killall nc')
        lan.expect(prompt)
