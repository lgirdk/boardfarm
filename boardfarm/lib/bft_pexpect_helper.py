import pexpect
import os
import sys
import time
import termcolor

IS_PYTHON_3 = sys.version_info > (3, 0)

from . import error_detect
from boardfarm.lib.bft_logging import o_helper

BFT_DEBUG = "BFT_DEBUG" in os.environ

def print_bold(msg):
    termcolor.cprint(msg, None, attrs=['bold'])

class bft_pexpect_helper(pexpect.spawn):
    '''
    Boardfarm helper for logging pexpect and making minor tweaks
    '''

    # Clean this up when we only have to support Python 3.
    if IS_PYTHON_3:
        class spawn(pexpect.spawn):
            def __init__(self, *args, **kwargs):
                kwargs['encoding'] = 'latin1'
                return pexpect.spawn.__init__(self, *args, **kwargs)
    else:
        spawn = pexpect.spawn

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
        if IS_PYTHON_3:
            kwargs['encoding'] = 'latin1'
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
            print_bold("%s = sending: %s" %
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
        print_bold("%s = expecting: %s" %
                          (error_detect.caller_file_line(idx), repr(pattern)))
        try:
            ret = wrapper(pattern, *args, **kwargs)

            frame = error_detect.caller_file_line(idx)

            if hasattr(self.match, "group"):
                print_bold("%s = matched: %s" %
                                  (frame, repr(self.match.group())))
            else:
                print_bold("%s = matched: %s" %
                                  (frame, repr(pattern)))
            return ret
        except:
            print_bold("expired")
            raise

    def expect(self, pattern, *args, **kwargs):
        wrapper = super(bft_pexpect_helper, self).expect

        return self.expect_helper(pattern, wrapper, *args, **kwargs)

    def expect_exact(self, pattern, *args, **kwargs):
        wrapper = super(bft_pexpect_helper, self).expect_exact

        return self.expect_helper(pattern, wrapper, *args, **kwargs)

    def sendcontrol(self, char):
        if BFT_DEBUG:
            print_bold("%s = sending: control-%s" %
                              (error_detect.caller_file_line(3), repr(char)))

        return super(bft_pexpect_helper, self).sendcontrol(char)

def spawn_ssh_pexpect(ip, user='root', pw='bigfoot1', prompt=None, port="22", via=None, color=None, o=sys.stdout, extra_args=""):
    """
    Provides a quick way to spawn an ssh session (this avoids having to import the SshConnection class from devices)
    Uses hardcoded options: -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null

    Parameters:
    ip:         ip address to ssh to
    user:       username used by ssh (default 'root')
    pw:         password (default 'bigfoot1')
    prompt:     expected prompt (default None, which creates one on the fly using the username in the "%s@.*$" pattern)
    port:       ssh port (default "22")
    via:        can be used to pass another pexpect session (default None, i.e. will ssh from localhost)
    color:      fonts output color (default None)
    o:          ssh output stream (defautl sys.stdout)
    extra_args: additional arguments APPENDED to the ssh command line (default "")
                E.g.: for a socks5 tunnnel with port 50000: extra_args="-D 50000 -N -v -v"
    """
    if via:
        p = via.sendline("ssh %s@%s -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s" \
                                            % (user, ip, port, extra_args))
        p = via
    else:
        p = bft_pexpect_helper.spawn("ssh %s@%s -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s" \
                                            % (user, ip, port, extra_args))

    i = p.expect(["yes/no", "assword:", "Last login"], timeout=30)
    if i == 0:
        p.sendline("yes")
        i = p.expect(["Last login", "assword:"])
    if i == 1:
        p.sendline(pw)
    else:
        pass

    if prompt is None:
        p.prompt = "%s@.*$" % user
    else:
        p.prompt = prompt

    p.expect(p.prompt)

    from termcolor import colored
    class o_helper_foo():
        def __init__(self, color):
            self.color = color
        def write(self, string):
            o.write(colored(string, color))
        def flush(self):
            o.flush()

    if color is not None:
        p.logfile_read = o_helper_foo(color)
    else:
        p.logfile_read = o

    return p


