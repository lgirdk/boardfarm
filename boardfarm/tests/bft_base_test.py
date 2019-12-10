# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time
from boardfarm import lib
import sys
import traceback

from boardfarm.library import check_devices
import boardfarm.exceptions
from boardfarm.devices import board, wan, lan, wlan
from boardfarm.lib.bft_logging import LoggerMeta, now_short

class BftBaseTest(object):
    _testMethodName = "UNDEFINED"
    __metaclass__ = LoggerMeta
    log = ""
    log_calls = ""
    _format = "%a %d %b %Y %H:%M:%S"

    def __init__(self, config):
        self.config = config
        self.test_args = getattr(config, "test_args", {})
        self.test_case_args = self.test_args.pop(type(self).__name__, {})
        self.reset_after_fail = True
        self.dont_retry = False
        self.logged = dict()
        self.subtests = []
        self.attempts = 0

    def id(self):
        return self.__class__.__name__

    def skipTest(self, reason):
        raise boardfarm.exceptions.SkipTest(reason)

    def startMarker(self):
        """Prints a banner at the beginning of a test, including the current time"""
        lib.common.test_msg("\n==================== Begin %s    Time: %s ====================" % (self.__class__.__name__, now_short(self._format)))

    def endMarker(self):
        """Prints a banner at the end of a test, including test status, number of attempts (if applicable) and the current time"""
        result = ""
        if self.attempts:
            result = self.result_grade + "(" + str(self.attempts ) + ")"
        lib.common.test_msg("\n==================== End %s   %s   Time: %s ==================" % (self.__class__.__name__, result, now_short(self._format)))

    def run(self):
        self.startMarker()
        self.testWrapper()
        self.endMarker()

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
            self.attempts = retry

            while retry >= 0:
                try:
                    self.runTest()
                    board.touch()
                    break
                except Exception as e:
                    retry = retry - 1
                    if(retry > 0):
                        self.attempts = self.config.retry - retry + 1
                        traceback.print_exc(file=sys.stdout)
                        print("\n\n----------- Test failed! Retrying in 5 seconds... -------------")
                        self.recover()
                        time.sleep(5)
                        print("=========== Retry attempt number %s of %s =============" % (self.attempts, self.config.retry))
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
            self.logged['test_time'] = float(self.stop_time - self.start_time)
        except boardfarm.exceptions.SkipTest:
            self.stop_time = time.time()
            self.logged['test_time'] = float(self.stop_time - self.start_time)
            self.result_grade = "SKIP"
            print("\n\n=========== Test skipped! Moving on... =============")
            return
        except Exception as e:
            self.stop_time = time.time()

            print("\n\n=========== Test: %s failed! running Device status check! Time: %s ===========" % (self.__class__.__name__, now_short(self._format)))
            try:
                all_devices = [board]+[getattr(self.config, name, None) for name in self.config.devices]
                check_devices(all_devices)
            except Exception as e:
                print(e)
            print("\n\n=========== Test: %s failed! Device status check done! Time: %s ===========" % (self.__class__.__name__, now_short(self._format)))

            self.logged['test_time'] = float(self.stop_time - self.start_time)
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
            self.endMarker()
            raise

    def recover(self):
        if self.__class__.__name__ == "BftBaseTest":
            print("aborting tests, unable to boot..")
            sys.exit(1)
        print("ERROR: No default recovery!")


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
            if 'feature' in device and feature in device['feature']:
                return getattr(self, device)

    def fetch_hosts(self):
        '''To fetch wan hosts
        Returns a dictionary of IP(key) with hosts(value) for all Wan devices'''
        import re
        hosts={}
        for device in self.config.devices:
            if  re.search("wan|sip|phone",device):
                dev = getattr(self.config, device)
                if hasattr(dev, 'iface_dut'):
                    device_ip = dev.get_interface_ipaddr(dev.iface_dut)
                    hosts[str(device_ip)]= device+".boardfarm.com"
        return hosts

    def execute_test_steps(self, prefix="", steps=[]):
        assert steps, "Please add steps to Test class before calling execute"
        for test_step in steps:
                if prefix: test_step.name = prefix + test_step.name
                with test_step:
                    test_step.execute()
