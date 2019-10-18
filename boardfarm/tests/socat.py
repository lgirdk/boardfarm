import re
from boardfarm.tests import rootfs_boot
from boardfarm.devices import board, wan, lan, prompt

from random import randint
import ipaddress
from faker import Factory
import pexpect
import re
import time
import random

fake_generator = Factory.create()

class SoCat(rootfs_boot.RootFSBootTest):
    '''Super simple simulatation of HTTP traffic'''

    all_ips = []
    all_conns = []

    conns = 100

    socat_recv = "TCP-LISTEN"
    socat_send = "TCP"
    payload = '"GET / HTTP/1.0\\r\\n\\r\\n"'

    def startSingleFlow(self, mintime=1, maxtime=60):
        while True:
            random_ip = fake_generator.ipv4()
            random_port = randint(1024, 65535)
            if not ipaddress.ip_address(random_ip.decode()).is_private:
                if (ipaddress.ip_address(random_ip.decode()), random_port) not in self.all_ips:
                    break
            else:
                print("Skipping ip addr: %s" % random_ip)
        print("Connecting to %s:%s" % (random_ip, random_port))

        self.all_ips.append((random_ip, random_port))

        # start listners
        wan.sendline('ip addr add %s/32 dev %s' % (random_ip, wan.iface_dut))
        wan.expect(prompt)

        random_rate = randint(1,1024)
        random_size = randint(int(1*random_rate*mintime), int(1024*random_rate*maxtime))

        args = (self.socat_recv, random_port, random_ip, self.payload, random_rate)
        wan.sendline("nohup socat %s:%s,bind=%s system:'(echo -n %s;  head /dev/zero) | pv -L %sk' &" % args)
        print("nohup socat %s:%s,bind=%s system:'(echo -n %s;  head /dev/zero) | pv -L %sk' &" % args)
        wan.expect(prompt)

        args = (self.payload, random_size, random_rate, self.socat_send, random_ip, random_port)
        lan.sendline("nohup socat system:'(echo -n %s;  head -c %s /dev/zero) | pv -L %sk' %s:%s:%s &" % args)
        print("nohup socat system:'(echo -n %s;  head -c %s /dev/zero) | pv -L %sk' %s:%s:%s &" % args)
        lan.expect(prompt)

        self.all_conns.append((random_size, random_rate, random_ip, random_port))
        return (random_size, random_rate, random_ip, random_port)

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
            print("Starting connection %s" % i)
            sz, rate, ip, port = self.startSingleFlow(maxtime=single_max)
            print("started flow to %s:%s sz = %s, rate = %sk" % (ip, port, sz, rate))

            max_time = max(max_time, sz / ( rate * 1024))
            self.check_and_clean_ips()

        print("waiting max time of %ss" % max_time)

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
        wan.sendline('ip addr del %s/32 dev %s' % (ip, wan.iface_dut))
        wan.expect_exact('ip addr del %s/32 dev %s' % (ip, wan.iface_dut))
        wan.expect(prompt)
        wan.sendline('pkill -9 -f socat.*bind=%s' % ip)
        wan.expect(prompt)
        lan.sendline('pkill -9 -f socat.*%s:%s' % (self.socat_send, ip))
        lan.expect(prompt)

    def check_and_clean_ips(self):
        if 'TCP' in self.socat_send:
            c = 'TCP'
        else:
            c = 'UDP'
        lan.sendline("echo SYNC; ps aux | grep  socat | sed -e 's/.*%s/%s/g' | tr '\n' ' '" % (c, c))
        lan.expect_exact("SYNC\r\n")
        lan.expect(prompt)
        seen_ips = re.findall('%s:([^:]*):' % self.socat_send, lan.before)

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
        print("mpstat cpu usage = %s" % self.logged['mpstat'])
        self.result_message = "BitTorrent test with %s connections, cpu usage = %s" % (self.conns, self.logged['mpstat'])


