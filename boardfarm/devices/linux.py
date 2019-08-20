import base, binascii
import os, ipaddress, re
from boardfarm.lib.regexlib import ValidIpv4AddressRegex, AllValidIpv6AddressesRegex, LinuxMacFormat
import pexpect

from common import print_bold

BFT_DEBUG = "BFT_DEBUG" in os.environ

class LinuxDevice(base.BaseDevice):
    '''Linux implementations '''
    tftp_dir = '/tftpboot'

    def get_interface_ipaddr(self, interface):
        '''Get ipv4 address of interface'''
        self.sendline("\nifconfig %s" % interface)
        regex = ['addr:(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(Bcast|P-t-P):',
                 'inet (\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(broadcast|P-t-P)',
                 'inet ('+ValidIpv4AddressRegex+').*netmask ('+ValidIpv4AddressRegex+').*destination '+ValidIpv4AddressRegex]
        self.expect(regex, timeout=5)
        ipaddr = self.match.group(1)
        ipv4address = str(ipaddress.IPv4Address(unicode(ipaddr)))
        self.expect(self.prompt)
        return ipv4address

    def get_interface_ip6addr(self, interface):
        '''Get ipv6 address of interface'''
        self.sendline("\nifconfig %s" % interface)
        self.expect_exact("ifconfig %s" % interface)
        self.expect(self.prompt)
        for match in re.findall(AllValidIpv6AddressesRegex, self.before):
            ip6address = ipaddress.IPv6Address(unicode(match))
            if not ip6address.is_link_local:
                return str(ip6address)
        raise Exception("Did not find non-link-local ipv6 address")

    def get_interface_macaddr(self, interface):
        '''Get the interface macaddress '''
        self.sendline('cat /sys/class/net/%s/address' % interface)
        self.expect_exact('cat /sys/class/net/%s/address' % interface)
        self.expect(LinuxMacFormat)
        macaddr = self.match.group()
        self.expect(self.prompt)
        return macaddr

    def get_seconds_uptime(self):
        '''Return seconds since last reboot. Stored in /proc/uptime'''
        self.sendcontrol('c')
        self.expect(self.prompt)
        self.sendline('\ncat /proc/uptime')
        self.expect('((\d+)\.(\d{2}))(\s)(\d+)\.(\d{2})')
        seconds_up = float(self.match.group(1))
        self.expect(self.prompt)
        return seconds_up

    def enable_ipv6(self, interface):
        '''Enable ipv6 of the interface '''
        self.sendline("sysctl net.ipv6.conf."+interface+".accept_ra=2")
        self.expect(self.prompt, timeout=30)
        self.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=0")
        self.expect(self.prompt, timeout=30)

    def disable_ipv6(self, interface):
        '''Disable ipv6 of the interface '''
        self.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=1")
        self.expect(self.prompt, timeout=30)

    def set_printk(self, CUR=1, DEF=1, MIN=1, BTDEF=7):
        '''Modifies the log level in kernel'''
        try:
            self.sendline('echo "%d %d %d %d" > /proc/sys/kernel/printk' % (CUR, DEF, MIN, BTDEF))
            self.expect(self.prompt, timeout=10)
            if not BFT_DEBUG:
                print_bold("printk set to %d %d %d %d" % (CUR, DEF, MIN, BTDEF))
        except:
            pass

    def prefer_ipv4(self, pref=True):
        """Edits the /etc/gai.conf file

        This is to give/remove ipv4 preference (by default ipv6 is preferred)
        See /etc/gai.conf inline comments for more details
        """
        if pref is True:
            self.sendline("sed -i 's/^#precedence ::ffff:0:0\/96  100/precedence ::ffff:0:0\/96  100/'  /etc/gai.conf")
        else:
            self.sendline("sed -i 's/^precedence ::ffff:0:0\/96  100/#precedence ::ffff:0:0\/96  100/'  /etc/gai.conf")
        self.expect(self.prompt)

    def ping(self, ping_ip, source_ip=None, ping_count=4, ping_interface=None):
        '''Check ping from any device'''
        if source_ip == None and ping_interface == None:
            self.sendline('ping -c %s %s' % (ping_count, ping_ip))
        elif ping_interface != None:
            self.sendline('ping -I %s -c %s %s' % (ping_interface, ping_count, ping_ip))
        else:
            self.sendline("ping -S %s -c %s %s" % (source_ip, ping_count, ping_ip))
        self.expect(self.prompt, timeout=50)
        match = re.search("%s packets transmitted, %s received, 0%% packet loss" %
                          (ping_count, ping_count), self.before)
        if match:
            return 'True'
        else:
            return 'False'

    def is_link_up(self, interface):
        '''Checking the interface status'''
        self.sendline("ip link show %s" % interface)
        self.expect(self.prompt)
        link_state = self.before
        match = re.search('BROADCAST,MULTICAST,UP',link_state)
        if match:
            return match.group(0)
        else:
            return None

    def set_link_state(self, interface, state):
        '''Setting the interface status'''
        self.sudo_sendline("ip link set %s %s" % (interface,state))
        self.expect(self.prompt)

    def add_new_user(self, id, pwd):
        '''Create new login ID. But check if already exists'''
        self.sendline('\nadduser %s' % id)
        try:
            self.expect_exact("Enter new UNIX password", timeout=5)
            self.sendline('%s' % pwd)
            self.expect_exact("Retype new UNIX password")
            self.sendline('%s' % pwd)
            self.expect_exact("Full Name []")
            self.sendline('%s' % id)
            self.expect_exact("Room Number []")
            self.sendline('1')
            self.expect_exact("Work Phone []")
            self.sendline('4081234567')
            self.expect_exact("Home Phone []")
            self.sendline('4081234567')
            self.expect_exact("Other []")
            self.sendline('4081234567')
            self.expect_exact("Is the information correct?")
            self.sendline('y')
            self.expect(self.prompt)
            self.sendline('usermod -aG sudo %s' % id)
            self.expect(self.prompt)
            # Remove "$" in the login prompt and replace it with "#"
            self.sendline('sed -i \'s/\\w\\\$ /\\\w# /g\' //home/%s/.bashrc' % id)
            self.expect(self.prompt, timeout=30)
        except:
            self.expect(self.prompt, timeout=30)

    def copy_file_to_server(self, src, dst=None):
        '''Copy the file from source to destination '''
        def gzip_str(string_):
            import gzip
            import io
            out = io.BytesIO()
            with gzip.GzipFile(fileobj=out, mode='w') as fo:
                fo.write(string_)
            return out.getvalue()

        with open(src, mode='rb') as file:
            bin_file = binascii.hexlify(gzip_str(file.read()))
        if dst is None:
            dst = self.tftp_dir + '/' + os.path.basename(src)
        print("Copying %s to %s" % (src, dst))
        saved_logfile_read = self.logfile_read
        self.logfile_read = None
        self.sendline('''cat << EOFEOFEOFEOF | xxd -r -p | gunzip > %s
%s
EOFEOFEOFEOF''' % (dst, bin_file))
        self.expect(self.prompt)
        self.sendline('ls %s' % dst)
        self.expect_exact('ls %s' % dst)
        i = self.expect(['ls: cannot access %s: No such file or directory' % dst] + self.prompt)
        if i == 0:
            raise Exception("Failed to copy file")
        self.logfile_read = saved_logfile_read

    def ip_neigh_flush(self):
        '''Removes entries in the neighbour table '''
        self.sendline('\nip -s neigh flush all')
        self.expect('flush all')
        self.expect(self.prompt)

    def sudo_sendline(self, cmd):
        '''Add sudo in the sendline if username is root'''
        if self.username != "root":
            self.sendline("sudo true")
            if 0 == self.expect(["password for .*:"] + self.prompt):
                 will_prompt_for_password = True
            else:
                 will_prompt_for_password = False

            cmd = "sudo " + cmd
            if will_prompt_for_password:
                self.sendline(self.password)
                self.expect(self.prompt)
        super(LinuxDevice, self).sendline(cmd)

    def set_cli_size(self, columns):
        '''Set the terminal colums value'''
        self.sendline('stty columns %s'%str(columns))
        self.expect(self.prompt)

    def wait_for_linux(self):
        '''Verify Linux starts up.'''
        i = self.expect(['Reset Button Push down', 'Linux version', 'Booting Linux', 'Starting kernel ...', 'Kernel command line specified:'], timeout=45)
        if i == 0:
            self.expect('httpd')
            self.sendcontrol('c')
            self.expect(self.uprompt)
            self.sendline('boot')
        i = self.expect(['U-Boot', 'login:', 'Please press Enter to activate this console'] + self.prompt, timeout=150)
        if i == 0:
            raise Exception('U-Boot came back when booting kernel')
        elif i == 1:
            self.sendline('root')
            if 0 == self.expect(['assword:'] + self.prompt):
                self.sendline('password')
                self.expect(self.prompt)

    def get_dns_server_upstream(self):
        '''Get the IP of name server'''
        self.sendline('cat /etc/resolv.conf')
        self.expect('nameserver (.*)\r\n', timeout=5)
        ret = self.match.group(1)
        self.expect(self.prompt)
        return ret

    def get_nf_conntrack_conn_count(self):
        '''Get the total number of connections in the network'''
        pp = self.get_pp_dev()

        for not_used in range(5):
            try:
                pp.sendline('cat /proc/sys/net/netfilter/nf_conntrack_count')
                pp.expect_exact('cat /proc/sys/net/netfilter/nf_conntrack_count', timeout=2)
                pp.expect(pp.prompt, timeout=15)
                ret = int(pp.before.strip())

                self.touch()
                return ret
            except:
                continue
            else:
                raise Exception("Unable to extract nf_conntrack_count!")

    def get_proc_vmstat(self, pp=None):
        '''Get the virtual machine status '''
        if pp is None:
            pp = self.get_pp_dev()

        for not_used in range(5):
            try:
                pp.sendline('cat /proc/vmstat')
                pp.expect_exact('cat /proc/vmstat')
                pp.expect(pp.prompt)
                results = re.findall('(\w+) (\d+)', pp.before)
                ret = {}
                for key, value in results:
                    ret[key] = int(value)

                return ret
            except Exception as e:
                print(e)
                continue
            else:
                raise Exception("Unable to parse /proc/vmstat!")

    def wait_for_network(self):
        '''Wait until network interfaces have IP Addresses.'''
        for interface in [self.wan_iface, self.lan_iface]:
            for i in range(5):
                try:
                    if interface is not None:
                        ipaddr = self.get_interface_ipaddr(interface).strip()
                        if not ipaddr:
                            continue
                        self.sendline("route -n")
                        self.expect(interface, timeout=2)
                        self.expect(self.prompt)
                except pexpect.TIMEOUT:
                    print("waiting for wan/lan ipaddr")
                else:
                    break

    def get_memfree(self):
        '''Return the kB of free memory.'''
        # free pagecache, dentries and inodes for higher accuracy
        self.sendline('\nsync; echo 3 > /proc/sys/vm/drop_caches')
        self.expect('drop_caches')
        self.expect(self.prompt)
        self.sendline('cat /proc/meminfo | head -2')
        self.expect('MemFree:\s+(\d+) kB')
        memFree = self.match.group(1)
        self.expect(self.prompt)
        return int(memFree)
