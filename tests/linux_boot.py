# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time
import unittest2
import lib
import sys
import traceback
import time

from devices import board, wan, lan, wlan, prompt
from lib.logging import LoggerMeta, now_short

class LinuxBootTest(unittest2.TestCase):
    _testMethodName = "UNDEFINED"
    __metaclass__ = LoggerMeta
    log = ""
    log_calls = ""
    _format = "%a %d %b %Y %H:%M:%S"

    def __init__(self, config):
        super(LinuxBootTest, self).__init__("testWrapper")
        self.config = config
        self.reset_after_fail = True
        self.dont_retry = False
        self.logged = dict()
        self.subtests = []

    def id(self):
        return self.__class__.__name__

    def setUp(self):
        lib.common.test_msg("\n==================== Begin %s    Time: %s ====================" % (self.__class__.__name__, now_short(self._format)))
    def tearDown(self):
        lib.common.test_msg("\n==================== End %s      Time: %s ======================" % (self.__class__.__name__, now_short(self._format)))

    def wan_setup(self):
        None

    def lan_setup(self):
        None

    def wlan_setup(self):
        None

    def wan_cleanup(self):
        None

    def lan_cleanup(self):
        None

    def wlan_cleanup(self):
        None

    def testWrapper(self):
        self.start_time = time.time()

        for d in self.config.devices:
            dev = getattr(self.config, d)
            dev.test_to_log = self
            dev.test_prefix = d.encode("utf8")

        for c in board.consoles:
            c.test_to_log = self
            c.test_prefix = 'console-%s' % str(board.consoles.index(c) + 1)

            if not c.isalive():
                self.result_grade = "SKIP"
                print("\n\n=========== Test skipped! Board is not alive... =============")
                self.skipTest("Board is not alive")
                raise

        try:
            if wan and hasattr(self, 'wan_setup'):
                self.wan_setup()
            if lan and hasattr(self, 'lan_setup'):
                self.lan_setup()
            if wlan and hasattr(self, 'wlan_setup'):
                self.wlan_setup()

            if self.config.retry and not self.dont_retry:
                retry = self.config.retry
            else:
                retry = 0

            while retry >= 0:
                try:
                    self.runTest()
                    board.touch()
                    retry = -1
                except Exception as e:
                    retry = retry - 1
                    if(retry > 0):
                        if hasattr(e, 'get_trace'):
                            print(e.get_trace())
                        else:
                            print("Exception has no trace, type = %s" % type(e))
                        print("\n\n----------- Test failed! Retrying in 5 seconds... -------------")
                        time.sleep(5)
                    else:
                        raise

            if wan and hasattr(self, 'wan_cleanup'):
                self.wan_cleanup()
            if lan and hasattr(self, 'lan_cleanup'):
                self.lan_cleanup()
            if wlan and hasattr(self, 'wlan_cleanup'):
                self.wlan_cleanup()

            if hasattr(self, 'expected_failure') and self.expected_failure:
                self.result_grade = "Unexp OK"
            else:
                self.result_grade = "OK"

            self.stop_time = time.time()
        except unittest2.case.SkipTest:
            self.stop_time = time.time()
            self.result_grade = "SKIP"
            print("\n\n=========== Test skipped! Moving on... =============")
            raise
        except Exception as e:
            self.stop_time = time.time()
            if hasattr(self, 'expected_failure') and self.expected_failure:
                self.result_grade = "Exp FAIL"
            else:
                self.result_grade = "FAIL"
            print("\n\n=========== Test failed! Running recovery Time: %s ===========" % now_short(self._format))
            if e.__class__.__name__ == "TIMEOUT":
                print(e.get_trace())
            else:
                print(e)
                traceback.print_exc(file=sys.stdout)

            import os
            if 'BFT_DEBUG' in os.environ:
                print(self)
                for device in self.config.devices:
                    d = getattr(self.config, device)
                    print(d)

            self.recover()
            raise

    def recover(self):
        if self.__class__.__name__ == "LinuxBootTest":
            print("aborting tests, unable to boot..")
            sys.exit(1)
        print("ERROR: No default recovery!")
        raise "No default recovery!"


    _log_to_file = None

    def x_log_to_file(self, value):
        pass

    def get_log_to_file(self):
        return self._log_to_file

    def set_log_to_file(self, value):
        # we have to call this because the property method calls are
        # not calling the decorator.. work around for now
        if self._log_to_file is not None:
            self.x_log_to_file(value.replace(self._log_to_file, ''))
        else:
            self.x_log_to_file(value)

        self._log_to_file = value

    log_to_file = property(get_log_to_file, set_log_to_file)

    def get_device_by_feature(self, feature):
        for device in self.config.devices:
            if 'feature' in device and feature in devices['feature']:
                return getattr(self, device)
