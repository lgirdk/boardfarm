# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import pexpect
from datetime import datetime
import re
import os
import time
import common
import error_detect
import ipaddress

from lib.regexlib import LinuxMacFormat, AllValidIpv6AddressesRegex
from lib.logging import LoggerMeta, o_helper

# To Do: maybe make this config variable
BFT_DEBUG = "BFT_DEBUG" in os.environ


class BaseDevice(pexpect.spawn):
    __metaclass__ = LoggerMeta
    log = ""
    log_calls = ""

    prompt = ['root\\@.*:.*#', ]
    delaybetweenchar = None

    def get_interface_ipaddr(self, interface):
        self.sendline("\nifconfig %s" % interface)
        self.expect('addr:(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(Bcast|P-t-P):', timeout=5)
        ipaddr = self.match.group(1)
        self.expect(self.prompt)
        return ipaddr

    def get_interface_ip6addr(self, interface):
        self.sendline("\nifconfig %s" % interface)
        self.expect_exact("ifconfig %s" % interface)
        self.expect(self.prompt)

        for match in re.findall(AllValidIpv6AddressesRegex, self.before):
            ip6addr = ipaddress.IPv6Address(unicode(match))
            if not ip6addr.is_link_local:
                # TODO: at some point just return ip6addr
                return match

        raise Exception("Did not find non-link-local ipv6 address")

    def get_interface_macaddr(self, interface):
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

    def get_logfile_read(self):
        if hasattr(self, "_logfile_read"):
            return self._logfile_read
        else:
            return None

    def expect_prompt(self, timeout=30):
        self.expect(self.prompt, timeout=timeout)

    def check_output(self, cmd, timeout=30):
        '''Send a string to device, then  return the output
        between that string and the next prompt.'''
        self.sendline("\n" + cmd)
        self.expect_exact(cmd, timeout=5)
        try:
            self.expect(self.prompt, timeout=timeout)
        except Exception as e:
            self.sendcontrol('c')
            raise Exception("Command did not complete within %s seconds. Prompt was not seen." % timeout)
        return self.before.strip()

    def write(self, string):
        self._logfile_read.write(string)

    def set_logfile_read(self, value):
        if value == None:
            self._logfile_read = None
            return

        if isinstance(value, o_helper):
            self._logfile_read = value
        elif value is not None:
            self._logfile_read = o_helper(self, value, getattr(self, "color", None))

    logfile_read = property(get_logfile_read, set_logfile_read)

    def interact(self, escape_character=chr(29),
                 input_filter=None, output_filter=None):

        o = self._logfile_read
        self.logfile_read = None
        ret = super(BaseDevice, self).interact(escape_character,
                                               input_filter, output_filter)
        self.logfile_read = o

        return ret

    # perf related
    def parse_sar_iface_pkts(self, wan, lan):
        self.expect('Average.*idle\r\nAverage:\s+all(\s+[0-9]+.[0-9]+){6}\r\n')
        idle = float(self.match.group(1))
        self.expect("Average.*rxmcst/s.*\r\n")

        wan_pps = None
        client_pps = None
        if lan is None:
            exp = [wan]
        else:
            exp = [wan, lan]

        for x in range(0, len(exp)):
            i = self.expect(exp)
            if i == 0:  # parse wan stats
                self.expect("(\d+.\d+)\s+(\d+.\d+)")
                wan_pps = float(self.match.group(1)) + float(self.match.group(2))
            if i == 1:
                self.expect("(\d+.\d+)\s+(\d+.\d+)")
                client_pps = float(self.match.group(1)) + float(self.match.group(2))

        return idle, wan_pps, client_pps

    def check_perf(self):
        self.sendline('uname -r')
        self.expect('uname -r')
        self.expect(self.prompt)

        self.kernel_version = self.before

        self.sendline('\nperf --version')
        i = self.expect(['not found', 'perf version'])
        self.expect(self.prompt)

        if i == 0:
            return False

        return True

    def check_output_perf(self, cmd, events):
        perf_args = self.perf_args(events)

        self.sendline("perf stat -a -e %s time %s" % (perf_args, cmd))

    def parse_perf(self, events):
        mapping = self.parse_perf_board()
        ret = []

        for e in mapping:
            if e['name'] not in events:
                continue
            self.expect("(\d+) %s" % e['expect'])
            e['value'] = int(self.match.group(1))
            ret.append(e)

        return ret

    # end perf related

    # Optional send and expect functions to try and be fancy at catching errors
    def send(self, s):
        if BFT_DEBUG:
            if 'pexpect/__init__.py: sendline():' in error_detect.caller_file_line(3):
                idx = 4
            else:
                idx = 3
            common.print_bold("%s = sending: %s" %
                              (error_detect.caller_file_line(idx), repr(s)))

        if self.delaybetweenchar is not None:
            ret = 0
            for char in s:
                ret += super(BaseDevice, self).send(char)
                time.sleep(self.delaybetweenchar)
            return ret

        return super(BaseDevice, self).send(s)

    def expect_helper(self, pattern, wrapper, *args, **kwargs):
        if not BFT_DEBUG:
            return wrapper(pattern, *args, **kwargs)

        if 'base.py: expect():' in error_detect.caller_file_line(3) or \
                'base.py: expect_exact():' in error_detect.caller_file_line(3):
            idx = 5
        else:
            idx = 3
        common.print_bold("%s = expecting: %s" %
                          (error_detect.caller_file_line(idx), repr(pattern)))
        try:
            ret = wrapper(pattern, *args, **kwargs)

            frame = error_detect.caller_file_line(idx)

            if hasattr(self.match, "group"):
                common.print_bold("%s = matched: %s" %
                                  (frame, repr(self.match.group())))
            else:
                common.print_bold("%s = matched: %s" %
                                  (frame, repr(pattern)))
            return ret
        except:
            common.print_bold("expired")
            raise

    def expect(self, pattern, *args, **kwargs):
        wrapper = super(BaseDevice, self).expect

        return self.expect_helper(pattern, wrapper, *args, **kwargs)

    def expect_exact(self, pattern, *args, **kwargs):
        wrapper = super(BaseDevice, self).expect_exact

        return self.expect_helper(pattern, wrapper, *args, **kwargs)

    def sendcontrol(self, char):
        if BFT_DEBUG:
            common.print_bold("%s = sending: control-%s" %
                              (error_detect.caller_file_line(3), repr(char)))

        return super(BaseDevice, self).sendcontrol(char)

    def expect_exact_split(self, pattern, nsplit=1, *args, **kwargs):
        pass

    def enable_ipv6(self, interface):
        self.sendline("sysctl net.ipv6.conf."+interface+".accept_ra=2")
        self.expect(self.prompt, timeout=30)
        self.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=0")
        self.expect(self.prompt, timeout=30)

    def disable_ipv6(self, interface):
        self.sendline("sysctl net.ipv6.conf."+interface+".disable_ipv6=1")
        self.expect(self.prompt, timeout=30)

    def set_printk(self, CUR=1, DEF=1, MIN=1, BTDEF=7):
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
