import base, binascii
import os, pexpect, ipaddress, re
from lib.regexlib import ValidIpv4AddressRegex, AllValidIpv6AddressesRegex, LinuxMacFormat

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
                common.print_bold("printk set to %d %d %d %d" % (CUR, DEF, MIN, BTDEF))
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
        print ("Copying %s to %s" % (src, dst))
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
