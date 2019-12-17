# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time
import types
from datetime import datetime
from termcolor import colored
import re
from functools import wraps

from boardfarm import start

def now_short(_format="%Y%m%d-%H%M%S"):
    """
    Name:now_short
    Purpose: Get current date and time string
    Input:None
    Output:String in "YYYYMMDD-hhmmss" format
    """
    timeString = time.strftime(_format, time.localtime()) + "\t"
    return timeString

def logfile_assert_message(s, condition, message):
    if not condition:
        s.log_to_file += now_short() + message + ": FAIL\r\n"
        assert 0, message + ": FAIL\r\n"
    else:
        log_message(s, message+": PASS")

class LoggerMeta(type):
    def __new__(cls, name, bases, attrs):
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, types.FunctionType):
                attrs[attr_name] = cls.deco(attr_value)

        return super(LoggerMeta, cls).__new__(cls, name, bases, attrs)

    @classmethod
    def deco(cls, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_args_str = "%s %s" % (repr(args), repr(kwargs))
            to_log = '%s.%s ( %s )' % (func.__module__, func.__name__, func_args_str)

            args[0].log_calls += '[%.6f]calling %s\r\n' % ((datetime.now() - start).total_seconds(), to_log)

            clsname = args[0].__class__.__name__

            # if the err_injection_dict exists, hijack the function call (if matched) and
            # return the bogus value.
            from boardfarm.config import get_err_injection_dict # TO DO:  remove once the ConfigHelper is fixed (i.e. is a sigleton)
            err_injection_dict = get_err_injection_dict()
            if err_injection_dict and clsname in err_injection_dict and func.__name__ in err_injection_dict[clsname]:
                ret = err_injection_dict[clsname][func.__name__]
                args[0].log_calls += "[%.6f]injecting %s = %s\r\n" % ((datetime.now() - start).total_seconds(), to_log, repr(ret))
            else:
                ret = func(*args, **kwargs)

            args[0].log_calls += "[%.6f]returned %s = %s\r\n" % ((datetime.now() - start).total_seconds(), to_log, repr(ret))

            return ret
        return wrapper

def log_message(s, msg, header=False):

    line_sep = ('=' * min(len(msg), 80))
    full_msg = "\n\t\t" + line_sep + "\n\t\t" + msg + "\n\t\t" + line_sep + "\n"
    if header:
        print("\n\n\t\t\t***" + msg + "***\n\n")
        s.log_to_file += now_short() + full_msg + "\r\n"
    else:
        print(full_msg)
        s.log_to_file += now_short() + msg + "\r\n"

class o_helper(object):
    def __init__(self, parent, out, color):
        self.color = color
        self.out = out
        self.parent = parent
        self.first_write = True
    def write(self, string):
        if self.first_write:
            self.first_write = False
            string = "\r\n" + string
        if self.color is not None:
            self.out.write(colored(string, self.color))
        else:
            self.out.write(string)
        td = datetime.now() - start
        # check for the split case
        if len(self.parent.log) > 1 and self.parent.log[-1] == '\r' and string[0] == '\n':
            tmp = '\n[%.6f]' % td.total_seconds()
            tmp += string[1:]
            string = tmp
        to_log = re.sub('\r\n', '\r\n[%.6f]' % td.total_seconds(), string)
        self.parent.log += to_log
        if hasattr(self.parent, 'test_to_log'):
            self.parent.test_to_log.log += re.sub('\r\n\[', '\r\n%s: [' % self.parent.test_prefix, to_log)
    def flush(self):
        self.out.flush()
