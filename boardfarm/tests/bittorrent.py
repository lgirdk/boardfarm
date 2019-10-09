# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import socat
import rootfs_boot
from boardfarm.devices import board, wan, lan, prompt

import pexpect

class BitTorrentBasic(socat.SoCat):
    '''Super simple simulation of BitTorrent traffic'''
    socat_recv = "UDP4-RECVFROM"
    socat_send = "UDP4-SENDTO"
    payload = "d1:ad2:id20:"

class BitTorrentSingle(BitTorrentBasic):
    '''Single UDP/Bittorrent flow'''

    def runTest(self):
        #for d in [wan, lan]:
            #d.sendline('apt-get update && apt-get -o Dpkg::Options::="--force-confnew" -y install socat pv')
            #d.expect(prompt)

        sz, rate, ip, port = self.startSingleFlow()
        print("started UDP to %s:%s sz = %s, rate = %sk" % (ip, port, sz, rate))
        time = sz / ( rate * 1024)
        print("time should be ~%s" % time)
        self.check_and_clean_ips()
        lan.sendline('fg')
        lan.expect(prompt, timeout=time+10)

        # TODO: make this a function that's more robust
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
            sz, rate, ip, port = self.startSingleFlow(maxtime=maxtime)
            print("started UDP to %s:%s sz = %s, rate = %sk" % (ip, port, sz, rate))
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
