import pexpect
import os
import time

from boardfarm.devices import error_detect
from boardfarm.lib import common
from boardfarm.lib.bft_logging import o_helper

BFT_DEBUG = "BFT_DEBUG" in os.environ

class bft_pexpect_helper(pexpect.spawn):
    '''
    Boardfarm helper for logging pexpect and making minor tweaks
    '''

    def __init__(self, *args, **kwargs):
        # Filters out boardfarm specific
        # Bad args that pexpext does not take, higher classes should have popped
        # them off, but we catch them all here in case
        bad_args = ['tftp_username', 'connection_type', 'power_password', 'rootfs',
                    'kernel', 'power_outlet', 'web_proxy', 'tftp_port', 'ssh_password',
                    'tftp_server', 'config', 'power_ip', 'conn_cmd', 'power_username',
                    'start', 'tftp_password']
        for arg in bad_args:
            kwargs.pop(arg)
        super(bft_pexpect_helper, self).__init__(*args, **kwargs)

    def get_logfile_read(self):
        if hasattr(self, "_logfile_read"):
            return self._logfile_read
        else:
            return None

    def set_logfile_read(self, value):
        if value == None:
            self._logfile_read = None
            return

        if isinstance(value, o_helper):
            self._logfile_read = value
        elif value is not None:
            self._logfile_read = o_helper(self, value, getattr(self, "color", None))

    logfile_read = property(get_logfile_read, set_logfile_read)

    def expect_prompt(self, timeout=30):
        self.expect(self.prompt, timeout=timeout)

    def check_output(self, cmd, timeout=30):
        '''Send a string to device, then  return the output
        between that string and the next prompt.'''
        self.sendline("\n" + cmd)
        self.expect_exact(cmd, timeout=5)
        try:
            self.expect(self.prompt, timeout=timeout)
        except Exception:
            self.sendcontrol('c')
            raise Exception("Command did not complete within %s seconds. Prompt was not seen." % timeout)
        return self.before.strip()

    def write(self, string):
        self._logfile_read.write(string)

    def interact(self, escape_character=chr(29),
                 input_filter=None, output_filter=None):

        o = self._logfile_read
        self.logfile_read = None
        ret = super(bft_pexpect_helper, self).interact(escape_character,
                                               input_filter, output_filter)
        self.logfile_read = o

        return ret

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
                ret += super(bft_pexpect_helper, self).send(char)
                time.sleep(self.delaybetweenchar)
            return ret

        return super(bft_pexpect_helper, self).send(s)

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
        wrapper = super(bft_pexpect_helper, self).expect

        return self.expect_helper(pattern, wrapper, *args, **kwargs)

    def expect_exact(self, pattern, *args, **kwargs):
        wrapper = super(bft_pexpect_helper, self).expect_exact

        return self.expect_helper(pattern, wrapper, *args, **kwargs)

    def sendcontrol(self, char):
        if BFT_DEBUG:
            common.print_bold("%s = sending: control-%s" %
                              (error_detect.caller_file_line(3), repr(char)))

        return super(bft_pexpect_helper, self).sendcontrol(char)


