# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
import ipaddress
import pexpect
import os
import time
import common
import error_detect
import signal
from lib.bft_logging import LoggerMeta, o_helper

# To Do: maybe make this config variable
BFT_DEBUG = "BFT_DEBUG" in os.environ


class BaseDevice(pexpect.spawn):
    __metaclass__ = LoggerMeta
    log = ""
    log_calls = ""

    prompt = ['root\\@.*:.*#', ]
    delaybetweenchar = None
    lan_gateway = ipaddress.IPv4Address(u"192.168.1.1")

    def get_interface_ipaddr(self, interface):
        '''Get ipv4 address of interface '''
        raise Exception("Not implemented!")

    def get_interface_ip6addr(self, interface):
        '''Get ipv6 address of interface '''
        raise Exception("Not implemented!")

    def get_interface_macaddr(self, interface):
        '''Get the interface mac address '''
        raise Exception("Not implemented!")

    def get_seconds_uptime(self):
        '''Return seconds since last reboot. Stored in /proc/uptime'''
        raise Exception("Not implemented!")

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

    def enable_ipv6(self, interface):
        '''Enable ipv6 in interface '''
        raise Exception("Not implemented!")

    def disable_ipv6(self, interface):
        '''Disable IPv6 in interface '''
        raise Exception("Not implemented!")

    def set_printk(self, CUR=1, DEF=1, MIN=1, BTDEF=7):
        '''Print the when debug enabled '''
        raise Exception("Not implemented!")

    def prefer_ipv4(self, pref=True):
        """Edits the /etc/gai.conf file

        This is to give/remove ipv4 preference (by default ipv6 is preferred)
        See /etc/gai.conf inline comments for more details
        """
        raise Exception("Not implemented!")

    def ping(self, ping_ip, source_ip=None, ping_count=4, ping_interface=None):
        '''Check Ping verification from device '''
        raise Exception("Not implemented!")

    def reset(self, break_into_uboot=False):
        '''Power-cycle this device.'''
        if not break_into_uboot:
            self.power.reset()
            return
        for attempt in range(3):
            try:
                self.power.reset()
                self.expect('U-Boot', timeout=30)
                self.expect('Hit any key ')
                self.sendline('\n\n\n\n\n\n\n') # try really hard
                self.expect(self.uprompt, timeout=4)
                # Confirm we are in uboot by typing any command.
                # If we weren't in uboot, we wouldn't see the command
                # that we type.
                self.sendline('echo FOO')
                self.expect('echo FOO', timeout=4)
                self.expect(self.uprompt, timeout=4)
                return
            except Exception as e:
                print(e)
                print("\nWe appeared to have failed to break into U-Boot...")

    def check_memory_addresses(self):
        '''Check/set memory addresses and size for proper flashing.'''
        raise Exception("Not implemented!")

    def flash_uboot(self, uboot):
        raise Exception('Code not written for flash_uboot for this board type, %s' % self.model)

    def flash_rootfs(self, ROOTFS):
        raise Exception('Code not written for flash_rootfs for this board type, %s' % self.model)

    def flash_linux(self, KERNEL):
        raise Exception('Code not written for flash_linux for this board type, %s.' % self.model)

    def flash_meta(self, META_BUILD, wan, lan):
        raise Exception('Code not written for flash_meta for this board type, %s.' % self.model)

    def prepare_nfsroot(self, NFSROOT):
        raise Exception('Code not written for prepare_nfsroot for this board type, %s.' % self.model)

    def kill_console_at_exit(self):
        '''killing console '''
        self.kill(signal.SIGKILL)

    def get_dns_server(self):
        '''Getting dns server ip address '''
        return "%s" % self.lan_gateway

    def touch(self):
        '''Keeps consoles active, so they don't disconnect for long running activities'''
        self.sendline()

    def boot_linux(self, rootfs=None, bootargs=""):
        raise Exception("\nWARNING: We don't know how to boot this board to linux "
              "please write the code to do so.")
