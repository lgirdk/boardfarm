import sys
import os
import ipaddress
import pexpect
from collections import OrderedDict, Counter

from boardfarm.lib.installers import install_wget, apt_install

class AFTR(object):
    '''
    Linux based DSLite server using ISC AFTR

    This profile class should be inherited along
    with a Linux Derived Class.
    '''

    model = ('aftr')
    aftr_dir = '/root/aftr'
    aftr_url = 'https://downloads.isc.org/isc/lwds-lite/1.0/rt28354.tbz'

    # this can be used to override behavior.
    # base device's method can be key.
    # e.g. Debian's configure method can call profile's configure method using self.profile['configure']
    profile = {}

    def __init__(self, *args, **kwargs):

        self.aftr_conf = OrderedDict()
        self.is_installed = False

        # IPv6 ep must be from a different subnet than WAN container.
        self.ipv6_ep = ipaddress.IPv6Interface(unicode(kwargs.get("ipv6_ep", "2001::1/48")))
        # Open gateway subnets need to be in this ACL.
        self.ipv6_ACL = [str(self.ipv6_ep.network), str(self.ipv6_interface.network)] + kwargs.get("ipv6_ACL",["2001:dead:beef::/48"])

        # this address will double NAT to WAN container's public IP
        self.ipv4_nat = ipaddress.IPv4Interface(unicode(kwargs.get("ipv4_nat","198.18.200.111/16")))
        self.ipv4_nat_ip = str(self.ipv4_nat.ip)

        # static pool port range
        self.ipv4_nat_pool = kwargs.get("ipv4_nat_pool","5000-59999")
        # dynamic pool port range
        self.ipv4_pcp_pool = kwargs.get("ipv4_pcp_pool","60000-64999")

        # default mss size is 1420
        self.mtu = kwargs.get("mss","1420")

        # local URL of aftr tarball. If we have an offline mirror.
        self.aftr_local = kwargs.get("local_site",None)
        self.aftr_fqdn = kwargs.get("aftr_fqdn", "aftr.boardfarm.com")

        self.profile["on_boot"] = self.configure_aftr
        self.profile["hosts"] = { "aftr.boardfarm.com" : str(self.ipv6_ep.ip) }

    def configure_aftr(self):
        self.install_aftr()
        start_conf = self.generate_aftr_conf()
        start_script = self.generate_aftr_script()

        run_conf = None
        # check if aftr.conf already exists
        self.sendline("ls /root/aftr/aftr.conf")
        if self.expect(["No such file or directory", pexpect.TIMEOUT], timeout=2) == 1:
            self.expect(self.prompt)
            self.sendline("cat /root/aftr/aftr.conf")
            self.expect(self.prompt)
            run_conf = [i.strip() for i in self.before.split("\n")[1:] if i.strip() != ""]
            self.sendline("\n")
        self.expect(self.prompt)

        run_script = None
        # check if aftr-script already exists
        self.sendline("ls /root/aftr/aftr-script")
        if self.expect(["No such file or directory", pexpect.TIMEOUT], timeout=2) == 1:
            self.expect(self.prompt)
            self.sendline("cat /root/aftr/aftr-script")
            self.expect(self.prompt)
            run_script = [i.strip() for i in self.before.split("\n")[1:] if i.strip() != ""]
            self.sendline("\n")
        self.expect(self.prompt)

        # if contents are same just restart the service.
        # will be useful incase we go with one aftr for a location.
        if Counter([i.strip() for i in start_conf.split("\n") if i.strip() != ""]) != Counter(run_conf):
            to_send = "cat > /root/aftr/aftr.conf << EOF\n%s\nEOF" % start_conf
            self.sendline(to_send)
            self.expect(self.prompt)

        # the replace is pretty static here, will figure out something later.
        if Counter([i.strip().replace("\$","$").replace("\`","`") for i in start_script.split("\n") if i.strip() != ""]) != Counter(run_script):
            to_send = "cat > /root/aftr/aftr-script << EOF\n%s\nEOF" % start_script
            self.sendline(to_send)
            self.expect(self.prompt)
            self.sendline("chmod +x /root/aftr/aftr-script")
            self.expect(self.prompt)

        # this part could be under a flagged condition.
        # forcing a reset since service is per board.
        self.sendline("killall aftr")
        self.expect(self.prompt)
        self.sendline("/root/aftr/aftr -c /root/aftr/aftr.conf -s /root/aftr/aftr-script")
        self.expect(self.prompt)

        self.expect(pexpect.TIMEOUT, timeout=2)
        assert str(self.get_interface_ipaddr("tun0")) == "192.0.0.1", "Failed to bring up tun0 interface."

    def generate_aftr_conf(self):
        '''
        Generates aftr.conf file.

        Refers conf/aftr.conf template inside ds-lite package.
        Returns:
        run_conf (str): Multiline string.
        '''
        run_conf = []

        # section 0 defines global paramters for NAT, PCP and tunnel.
        # If not specified, aftr script will consider it's default values.
        self.aftr_conf["section 0: global parameters"]= OrderedDict([
                ("defmtu " , self.mtu),
                ("defmss " , "on"),
                # dont't throw error if IPv4 packet is too big to fit in one IPv6 encapsulating packet
                ("deftoobig " , "off")
                ])

        # section 1 defines required parameters.
        # providing minimum requirement to bring up aftr tunnel.
        self.aftr_conf["section 1: required parameters"]= OrderedDict([
                ("address endpoint " , str(self.ipv6_ep.ip)),
                ("address icmp " , self.ipv4_nat_ip),
                ("pool %s tcp " % self.ipv4_nat_ip , self.ipv4_nat_pool),
                ("pool %s udp " % self.ipv4_nat_ip , self.ipv4_nat_pool),
                ("pcp %s tcp " % self.ipv4_nat_ip , self.ipv4_pcp_pool),
                ("pcp %s udp " % self.ipv4_nat_ip , self.ipv4_pcp_pool),
                ("#All IPv6 ACLs\n" , "\n".join(map( lambda x: "acl6 %s" % x, self.ipv6_ACL )))
                ])

        for k,v in self.aftr_conf.iteritems():
            run_conf.append("## %s\n" % k)
            for option,value in v.iteritems():
                run_conf.append("%s%s" % (option,value))
            run_conf[-1] += "\n"

        return "\n".join(run_conf)

    def generate_aftr_script(self):
        """
        Generates aftr-httpserverscript.

        Refers conf/aftr-script.linux template inside ds-lite package.
        Returns:
        script (str): Multiline string.
        """
        tab = "    "

        script = "#!/bin/sh\n\n"
        run_conf = OrderedDict()

        # added a few sysctls to get it working inside a container.
        run_conf["aftr_start()"] = "\n".join(map( lambda x: "%s%s" % (tab,x),
            [
                "ip link set tun0 up",
                "sysctl -w net.ipv4.ip_forward=1",
                "sysctl -w net.ipv6.conf.all.forwarding=1",
                "sysctl -w net.ipv6.conf.all.disable_ipv6=0",
                "ip addr add 192.0.0.1 peer 192.0.0.2 dev tun0",
                "ip route add %s dev tun0" % str(self.ipv4_nat.network),
                "ip -6 route add %s dev tun0" % str(self.ipv6_ep.network),
                "iptables -t nat -F",
                "iptables -t nat -A POSTROUTING -s %s -j SNAT --to-source \$PUBLIC" % self.ipv4_nat_ip,
                "iptables -t nat -A PREROUTING -p tcp -d \$PUBLIC --dport %s -j DNAT --to-destination %s" % (self.ipv4_pcp_pool.replace("-",":"),self.ipv4_nat_ip),
                "iptables -t nat -A PREROUTING -p udp -d \$PUBLIC --dport %s -j DNAT --to-destination %s" % (self.ipv4_pcp_pool.replace("-",":"),self.ipv4_nat_ip),
                "iptables -t nat -A OUTPUT -p tcp -d \$PUBLIC --dport %s -j DNAT --to-destination %s" % (self.ipv4_pcp_pool.replace("-",":"),self.ipv4_nat_ip),
                "iptables -t nat -A OUTPUT -p udp -d \$PUBLIC --dport %s -j DNAT --to-destination %s" % (self.ipv4_pcp_pool.replace("-",":"),self.ipv4_nat_ip)
            ]))

        run_conf["aftr_stop()"] = "\n".join(map( lambda x: "%s%s" % (tab,x),
            [
                "iptables -t nat -F",
                "ip link set tun0 down"
            ]))

        extra_bits = "\n".join([
                "set -x",
                "PUBLIC=\`ip addr show dev %s | grep -w inet | awk '{print \$2}' | awk -F/ '{print \$1}'\`" % self.iface_dut,
                '\ncase "\$1" in',
                "start)",
                "%saftr_start" % tab, "%s;;" % tab,
                "stop)",
                "%saftr_stop" % tab, "%s;;" % tab,
                "*)",
                '%secho "Usage: \$0 start|stop"' % tab, "%sexit 1" % tab ,"%s;;" % tab,
                "esac\n",
                "exit 0"
            ])

        # there could be a better way to generate this shell script.
        script += "%s\n%s" % ("\n".join([ "%s\n{\n%s\n}" % (k,v) for k,v in run_conf.iteritems()]),extra_bits)
        return script

    def install_aftr(self):
        # check for aftr executable
        attempt = 0
        while attempt < 2:
            self.sendline("ls /root/aftr/aftr")
            if self.expect(["No such file or directory", pexpect.TIMEOUT], timeout=2) == 0:
                self.expect(self.prompt)
                apt_install(self, 'build-essential')
                # check for configure script.
                self.sendline("ls /root/aftr/configure")
                if self.expect(["No such file or directory", pexpect.TIMEOUT], timeout=2) == 0:
                    self.expect(self.prompt)
                    # need to download the tar file and extract it.
                    install_wget(self)
                    self.aftr_url = self.aftr_local if self.aftr_local is not None else self.aftr_url
                    self.sendline("wget %s -O /root/aftr.tbz" % self.aftr_url)
                    self.expect(self.prompt, timeout=60)
                    self.sendline("tar -C /root -xvjf /root/aftr.tbz; mv /root/rt28354 /root/aftr")
                self.expect(self.prompt, timeout=30)
                self.sendline("cd /root/aftr")
                self.expect(self.prompt)
                self.sendline("./configure")
                self.expect(self.prompt, timeout=30)
                self.sendline("make; cd")
                self.expect(self.prompt, timeout=30)
                attempt += 1
            else:
                self.is_installed = True
                self.expect(self.prompt)
                break

        if not self.is_installed:
            raise Exception("failed to install AFTR.")

    def enable_aftr(self):
        pass

    def disable_aftr(self):
        pass


if __name__ == '__main__':
    # Example use
    try:
        ipaddr, port = sys.argv[1].split(':')
    except:
        raise Exception("First argument should be in form of ipaddr:port")

    # for getting lib.common from tests working
    sys.path.append(os.getcwd() + '/../')
    sys.path.append(os.getcwd() + '/../tests')

    # get a base class to work with AFTR profile class.
    from debian import DebianBox as BaseCls
    class BfNode(BaseCls, AFTR):
        def __init__(self,*args,**kwargs):
            BaseCls.__init__(self,*args,**kwargs)
            AFTR.__init__(self,*args,**kwargs)

    dev = BfNode(ipaddr=ipaddr,
            color='blue',
            username="root",
            password="bigfoot1",
            port=port,
            options="tftpd-server, wan-static-ip:10.64.38.23/23, wan-no-eth0, wan-static-ipv6:2001:730:1f:60a::cafe:23, static-route:0.0.0.0/0-10.64.38.2")

    dev.configure("wan_device")
    dev.profile["on_boot"]()
