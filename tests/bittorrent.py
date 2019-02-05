# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import re
import rootfs_boot
from devices import board, wan, lan, prompt

from random import randint
import socket
import struct
import ipaddress
from faker import Factory
import pexpect
import re
import time
import random

fake_generator = Factory.create()

class BitTorrentBasic(rootfs_boot.RootFSBootTest):
    '''Super basic simulate of bittorrent traffic'''

    all_ips = []
    all_conns = []

    conns = 100

    def startSingleUDP(self, mintime=1, maxtime=60):
        while True:
            random_ip = fake_generator.ipv4()
            random_port = randint(1024, 65535)
            if not ipaddress.ip_address(random_ip.decode()).is_private:
                if (ipaddress.ip_address(random_ip.decode()), random_port) not in self.all_ips:
                    break
            else:
                print ("Skipping ip addr: %s" % random_ip)
        print("Connecting to %s:%s" % (random_ip, random_port))

        self.all_ips.append((random_ip, random_port))

        # start listners
        wan.sendline('ip addr add %s/32 dev eth1' % random_ip)
        wan.expect(prompt)

        random_rate = randint(1,1024)
        random_size = randint(int(1*random_rate*mintime), int(1024*random_rate*maxtime))

        wan.sendline("nohup socat UDP4-RECVFROM:%s,bind=%s system:'(echo -n d1:ad2:id20:;  head /dev/zero) | pv -L %sk' &" % (random_port, random_ip, random_rate))
        wan.expect(prompt)

        args = (random_size, random_rate, random_ip, random_port)
        lan.sendline("nohup socat system:'(echo -n d1:ad2:id20:;  head -c %s /dev/zero) | pv -L %sk' UDP4-SENDTO:%s:%s &" % args)
        lan.expect(prompt)

        self.all_conns.append(args)
        # size, rate, ip, port
        return args

    def runTest(self):
        random.seed(99)

        for d in [wan, lan]:
            d.sendline('apt-get update && apt-get -o Dpkg::Options::="--force-confnew" -y install socat pv')
            d.expect(prompt)

        max_time = 0
        single_max = 45

        board.collect_stats(stats=['mpstat'])

        # TODO: query interfaces but this is OK for now
        for i in range(self.conns):
            board.get_nf_conntrack_conn_count()
            board.touch()
            print ("Starting connection %s" % i)
            sz, rate, ip, port = self.startSingleUDP(maxtime=single_max)
            print ("started UDP to %s:%s sz = %s, rate = %sk" % (ip, port, sz, rate))

            max_time = max(max_time, sz / ( rate * 1024))
            self.check_and_clean_ips()

        print ("waiting max time of %ss" % max_time)

        start = time.time()
        while time.time() - start < max_time + 5:
            lan.sendline('wait')
            lan.expect_exact('wait')
            lan.expect([pexpect.TIMEOUT] + prompt, timeout=5)
            lan.sendcontrol('c')
            lan.expect(prompt)
            self.check_and_clean_ips()
            board.get_nf_conntrack_conn_count()
            board.touch()

        self.recover()

    def cleanup_ip(self, ip):
        wan.sendline('ip addr del %s/32 dev eth1' % ip)
        wan.expect_exact('ip addr del %s/32 dev eth1' % ip)
        wan.expect(prompt)
        wan.sendline('pkill -9 -f socat.*bind=%s' % ip)
        wan.expect(prompt)
        lan.sendline('pkill -9 -f socat.*UDP4-SENDTO:%s' % ip)
        lan.expect(prompt)

    def check_and_clean_ips(self):
        lan.sendline("echo SYNC; ps aux | grep  socat | sed -e 's/.*UDP/UDP/g' | tr '\n' ' '")
        lan.expect_exact("SYNC\r\n")
        lan.expect(prompt)
        seen_ips = re.findall('UDP4-SENDTO:([^:]*):', lan.before)

        if len(self.all_ips) > 0:
            ips_to_cleanup = set(zip(*self.all_ips)[0]) - set(seen_ips)
            for done_ip in ips_to_cleanup:
                self.cleanup_ip(done_ip)
                self.all_ips = [e for e in self.all_ips if e[0] != done_ip ]

    def recover(self):
        wan.sendcontrol('c')
        wan.expect(prompt)
        wan.sendline('killall -9 socat pv')
        wan.expect_exact('killall -9 socat pv')
        wan.expect(prompt)

        for d in [wan, lan]:
            d.sendcontrol('c')
            d.expect(prompt)
            d.sendline('pgrep -f d1:ad2:id20')
            d.expect_exact('pgrep -f d1:ad2:id20')
            d.expect(prompt)
            d.sendline('pkill -9 -f d1:ad2:id20')
            d.expect_exact('pkill -9 -f d1:ad2:id20')
            d.expect(prompt)
            d.sendline('killall -9 socat')
            d.expect_exact('killall -9 socat')
            d.expect(prompt)

        for ip, port in self.all_ips:
            self.cleanup_ip(ip)

        # this needs to be here because we need to make sure mpstat is cleaned up
        board.parse_stats(dict_to_log=self.logged)
        print ("mpstat cpu usage = %s" % self.logged['mpstat'])
        self.result_message = "BitTorrent test with %s connections, cpu usage = %s" % (self.conns, self.logged['mpstat'])

class BitTorrentSingle(BitTorrentBasic):
    '''Single UDP/Bittorrent flow'''

    def runTest(self):
        #for d in [wan, lan]:
            #d.sendline('apt-get update && apt-get -o Dpkg::Options::="--force-confnew" -y install socat pv')
            #d.expect(prompt)

        sz, rate, ip, port = self.startSingleUDP()
        print ("started UDP to %s:%s sz = %s, rate = %sk" % (ip, port, sz, rate))
        time = sz / ( rate * 1024)
        print("time should be ~%s" % time)
        self.check_and_clean_ips()
        lan.sendline('fg')
        lan.expect(prompt, timeout=time+10)

        board.get_pp_dev().sendline('cat /proc/net/nf_conntrack | grep dst=%s.*dport=%s' % (ip, port))
        board.get_pp_dev().expect(prompt)

        self.recover()

class BitTorrentB2B(BitTorrentBasic):
    '''Single UDP/Bittorrent flow back-to-back'''

    def runTest(self):
        #for d in [wan, lan]:
            #d.sendline('apt-get update && apt-get -o Dpkg::Options::="--force-confnew" -y install socat pv')
            #d.expect(prompt)

	maxtime=5

        board.get_nf_conntrack_conn_count()

	for i in range(10000):
	    sz, rate, ip, port = self.startSingleUDP(maxtime=maxtime)
	    print ("started UDP to %s:%s sz = %s, rate = %sk" % (ip, port, sz, rate))
	    time = sz / ( rate * 1024)
	    print("time should be ~%s" % time)
            self.check_and_clean_ips()
	    lan.sendline('fg')
	    lan.expect(prompt, timeout=5)

	    board.get_pp_dev().sendline('cat /proc/net/nf_conntrack | grep dst=%s.*dport=%s' % (ip, port))
	    board.get_pp_dev().expect(prompt)

        board.get_nf_conntrack_conn_count()

        self.recover()

class BitTorrentClient(rootfs_boot.RootFSBootTest):
    def runTest(self):
        board.sendcontrol('c')
        board.expect(board.prompt)
        board.sendline('logread -f &')
        board.expect(board.prompt)

        lan.sendline('rm -rf Fedora*')
        lan.expect(lan.prompt)
        # TODO: apt-get install bittornado
        for i in range(10):
            lan.sendline("btdownloadheadless 'https://torrent.fedoraproject.org/torrents/Fedora-Games-Live-x86_64-28_Beta.torrent'")
            lan.expect('saving:')
            done = False
            while not done:
                lan.expect(pexpect.TIMEOUT, timeout=1) # flush buffer
                if 0 == lan.expect(['time left:      Download Succeeded!', pexpect.TIMEOUT], timeout=10):
                    print("Finished, restarting....")
                    done = True
                board.expect(pexpect.TIMEOUT, timeout=5)
                board.sendline() # keepalive
            lan.sendcontrol('c')
            lan.sendcontrol('c')
            lan.sendcontrol('c')
            lan.expect(lan.prompt)
            lan.sendline('rm -rf Fedora*')
            lan.expect(lan.prompt)

    def recover(self):
        lan.sendcontrol('c')
        lan.expect(lan.prompt)
        lan.sendline('rm -rf Fedora*')
        lan.expect(lan.prompt)
        board.sendcontrol('c')
        board.expect(board.prompt)
        board.sendline('fg')
        board.sendcontrol('c')
        board.expect(board.prompt)
