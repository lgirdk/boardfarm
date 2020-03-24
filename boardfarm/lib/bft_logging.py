# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import re
import time
import types
from functools import wraps

from termcolor import colored


def now_short(_format="%Y%m%d-%H%M%S"):
    """Get current date and time string

    :param _format: time stamp format, defaults to "%Y%m%d-%H%M%S"
    :type _format: string, optional
    :return: timestamp in YYYYMMDD-hhmmss
    :rtype: string
    """
    timeString = time.strftime(_format, time.localtime()) + "\t"
    return timeString


def logfile_assert_message(s, condition, message):
    """Function to log and assert based on condition.
    If condition True, log message as PASS to testcase log file.
    If condition False, Assert and Print message with status FAIL.

    :param s: Instance of the class
    :type s: Class
    :param condition: condition to validate
    :type condition: Condition
    :param message: Message to log and print
    :type message: String
    :raise assertion: Assert on condition is FALSE
    """
    if not condition:
        s.log_to_file += now_short() + message + ": FAIL\r\n"
        assert 0, message + ": FAIL\r\n"
    else:
        log_message(s, message + ": PASS")


def write_test_log(t, output_dir):
    '''
    Write detailed log file for given test.
    '''
    if t.log_to_file is not None and hasattr(t, 'stop_time'):
        filename = type(t).__name__ + '-' + time.strftime(
            "%Y%m%d-%H%M%S") + ".txt"
        testtime = t.stop_time - t.start_time
        with open(os.path.join(output_dir, filename), 'w') as log:
            log.write(
                '\t=======================================================')
            log.write('\n\tTest case ID: %s' % (type(t).__name__))
            log.write('\n\tTest case Description: %s' % (type(t).__doc__))
            log.write(
                '\n\t=======================================================\n'
            )
            log.write(t.log_to_file)
            log.write(
                '\n\t=======================================================')
            log.write('\n\t%s test result: %s' %
                      (type(t).__name__, t.result_grade))
            log.write('\n\tTotal test time: %s seconds' % testtime)
            log.write(
                '\n\t=======================================================')


class LoggerMeta(type):
    def __new__(cls, name, bases, attrs):
        """Magic method to create instance object reference.
        Using this method you can customize the instance creation.

        :param cls: Class to be instantiated(LoggerMeta)
        :type cls: Class
        :param name: name of the new Class instantiated
        :type name: Class
        :param bases: Tuple of base parent classes
        :type bases: Class
        :param attrs: Class attributes
        :type attrs: Arguments(args)
        :return: Return the instance object created
        :rtype: Object

        """
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, types.FunctionType):
                attrs[attr_name] = cls.deco(attr_value)

        return super(LoggerMeta, cls).__new__(cls, name, bases, attrs)

    @classmethod
    def deco(cls, func):
        """This method writes functions calls to log file with time

        :param cls: Instance of the class LoggerMeta
        :type cls: Class
        :param func: function called this method
        :type func: Object
        :return: Return of the called function
        :rtype: string
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            """Wrapper function that parses the calling function arguments and send to logs with date time

            :param args: any number of extra arguments
            :type args: Arguments(args)
            :param kwargs: arguments, where you provide a name to the variable as you pass it into the function
            :type kwargs: Arguments(args)
            :return: String with parent class, calling/returning of function
            :rtype: string
            """
            func_args_str = "%s %s" % (repr(args), repr(kwargs))
            to_log = '%s.%s ( %s )' % (func.__module__, func.__name__,
                                       func_args_str)

            args[0].log_calls += '[%.6f]calling %s\r\n' % (time.process_time(),
                                                           to_log)

            clsname = args[0].__class__.__name__

            # if the err_injection_dict exists, hijack the function call (if matched) and
            # return the bogus value.
            from boardfarm.config import get_err_injection_dict  # TO DO:  remove once the ConfigHelper is fixed (i.e. is a sigleton)
            err_injection_dict = get_err_injection_dict()
            if err_injection_dict and clsname in err_injection_dict and func.__name__ in err_injection_dict[
                    clsname]:
                ret = err_injection_dict[clsname][func.__name__]
                args[0].log_calls += "[%.6f]injecting %s = %s\r\n" % (
                    time.processs_time(), to_log, repr(ret))

            else:
                ret = func(*args, **kwargs)

            args[0].log_calls += "[%.6f]returned %s = %s\r\n" % (
                time.process_time(), to_log, repr(ret))

            return ret

        return wrapper


def log_message(s, msg, header=False):
    """Write log messages to console and to log file(with timestamp)

    :param s: Instance of the class
    :type s: Class
    :param msg: Message to log and print
    :type msg: String
    :param header: True or False, defaults to False. To display message as header
    :type header: Boolean, Optional
    """

    if s.log_to_file is None:
        s.log_to_file = ""

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
        """Constructor method to handle the output logging

        :param parent: Parent class
        :type parent: Class
        :param out: Output stream (stdout)
        :type out: Streams
        :param color: text colour for the device(provided in Json)
        :type color: String
        """
        self.color = color
        self.out = out
        self.parent = parent
        self.first_write = True

    def write(self, string):
        """Writes or stdout input messages in colored(if defined).
        Create the file if not already present.
        For example: <Testcase>.txt file creation

        :param string: Message to write in the output file
        :type string: String
        """
        if self.out is not None:
            if self.first_write:
                self.first_write = False
                string = "\r\n" + string
            if self.color is not None:
                self.out.write(colored(string, self.color))
            else:
                self.out.write(string)
        # check for the split case
        if len(self.parent.log
               ) > 1 and self.parent.log[-1] == '\r' and string[0] == '\n':
            tmp = '\n[%.6f]' % time.process_time()
            tmp += string[1:]
            string = tmp
        to_log = re.sub('\r\n', '\r\n[%.6f]' % time.process_time(), string)
        self.parent.log += to_log
        if hasattr(self.parent, 'test_to_log'):
            self.parent.test_to_log.log += re.sub(
                '\r\n\[', '\r\n%s: [' % self.parent.test_prefix, to_log)

    def extra_log(self, string):
        if hasattr(self.parent, 'log'):
            self.parent.log += "\r\n[%s] " % time.process_time()
            self.parent.log += string + '\r\n'

    def flush(self):
        """Flushes the buffer storage in console before pexpect"""
        if self.out is not None:
            self.out.flush()


def create_file_logs(config, board, tests_to_run, logger):
    combined_list = []

    def add_to_combined_list(log, name, combined_list=combined_list):
        for line in log.split('\r\n'):
            try:
                if line == '':
                    continue
                if line.startswith('\n'):
                    line = line[1:]
                if line.startswith(' ['):
                    line = line[1:]
                ts, text = line.split(']', 1)
                combined_list.append({
                    "time": float(ts[1:-1]),
                    "text": str(text),
                    "name": name
                })
            except:
                logger.debug("Failed to parse log line = %s" % repr(line))
                pass

    idx = 1
    console_combined = []
    for console in board.consoles:
        with open(os.path.join(config.output_dir, 'console-%s.log' % idx),
                  'w') as clog:
            clog.write(console.log)
            add_to_combined_list(console.log, "console-%s" % idx)
            add_to_combined_list(console.log_calls, "console-%s" % idx)
            add_to_combined_list(console.log, "", console_combined)
        idx = idx + 1

    def write_combined_log(combined_list, fname):
        with open(os.path.join(config.output_dir, fname), 'w') as clog:
            for e in combined_list:
                try:
                    if e['name'] == "":
                        clog.write('[%s]%s\r\n' % (e['time'], repr(e['text'])))
                    else:
                        clog.write('%s: [%s] %s\n' %
                                   (e['name'], e['time'], repr(e['text'])))
                except:
                    logger.debug("failed to parse line: %s" % repr(e))

    import operator
    console_combined.sort(key=operator.itemgetter('time'))
    write_combined_log(console_combined, "console-combined.log")

    for device in config.devices:
        with open(os.path.join(config.output_dir, device + ".log"),
                  'w') as clog:
            d = getattr(config, device)
            if hasattr(d, 'log'):
                clog.write(d.log)
                add_to_combined_list(d.log, device)
                add_to_combined_list(d.log_calls, device)

    for test in tests_to_run:
        if hasattr(test, 'log') and test.log != "":
            with open(
                    os.path.join(config.output_dir,
                                 '%s.log' % test.__class__.__name__),
                    'w') as clog:
                clog.write(test.log)
        if hasattr(test, 'log_calls'):
            add_to_combined_list(test.log_calls, test.__class__.__name__)

    combined_list.sort(key=operator.itemgetter('time'))
    write_combined_log(combined_list, "all.log")
