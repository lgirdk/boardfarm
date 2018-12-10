# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time
import types
from datetime import datetime

def now_short():
    """
    Name:now_short
    Purpose: Get current date and time string
    Input:None
    Output:String in "YYYYMMDD-hhmmss" format
    """
    timeString = time.strftime("%Y%m%d-%H%M%S", time.localtime())+"\t"
    return timeString

def logfile_assert_message(s, condition, message):
	if not condition:
	   s.log_to_file += now_short()+message+": FAIL\r\n"
	   assert 0, message+": FAIL\r\n"
	else:
	   s.log_to_file += now_short()+message+": PASS\r\n"

class LoggerMeta(type):
    def __new__(cls, name, bases, attrs):
        for attr_name, attr_value in attrs.iteritems():
            if isinstance(attr_value, types.FunctionType):
                attrs[attr_name] = cls.deco(attr_value)

        return super(LoggerMeta, cls).__new__(cls, name, bases, attrs)

    @classmethod
    def deco(cls, func):
        def wrapper(*args, **kwargs):
            func_args_str = "%s %s" % (repr(args), repr(kwargs))
            to_log = '%s.%s ( %s )' % (func.__module__, func.__name__, func_args_str)

            if hasattr(args[0], 'start'):
                args[0].log_calls += '[%s]calling %s\r\n' % ((datetime.now()-args[0].start).total_seconds(), to_log)

            ret = func(*args, **kwargs)

            if hasattr(args[0], 'start'):
                args[0].log_calls += "[%s]returned %s = %s\r\n" % ((datetime.now()-args[0].start).total_seconds(), to_log, repr(ret))

            return ret
        return wrapper
