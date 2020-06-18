# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import sys
import time
import traceback
import warnings

import boardfarm.config
import boardfarm.exceptions
import boardfarm.lib.ConfigHelper
import boardfarm.lib.DeviceManager
import boardfarm.lib.env_helper
import boardfarm.lib.test_configurator
import debtcollector
import six
from boardfarm import lib
from boardfarm.lib.bft_logging import LoggerMeta, now_short
from boardfarm.library import check_devices
from boardfarm.orchestration import TearDown
from unittest2 import TestCase as UTest

warnings.simplefilter("always", UserWarning)


class _UnitTestCls(UTest):
    def __init__(self, *args, **kwargs):
        # This is just to ensure the pytest runs with BF
        # this is done so that base prefixed/suffixed test method don't run
        UTest.__init__(self, 'test_main')
        print('Args passed while running with pytest: {}'.format(
            [self.config, self.dev, self.env_helper]))


_using_pytest = False
if "pytest" in sys.modules:
    import pytest
    inherit_class = _UnitTestCls
    _using_pytest = True
else:
    inherit_class = six.with_metaclass(LoggerMeta, object)


class BftBaseTest(inherit_class):
    _testMethodName = "UNDEFINED"
    log = ""
    log_calls = ""
    _format = "%a %d %b %Y %H:%M:%S"
    start_time = 0
    stop_time = 0

    def __init__(self, *args, **kwargs):
        self.config = self.dev = self.env_helper = None
        if args and len(args) == 3:
            if type(
                    args[0]
            ) is boardfarm.lib.test_configurator.BoardfarmTestConfig or args[
                    0] is boardfarm.config:
                self.config = args[0]
            if type(args[1]) is boardfarm.lib.DeviceManager.device_manager:
                self.dev = args[1]
            if issubclass(type(args[2]), boardfarm.lib.env_helper.EnvHelper):
                self.env_helper = args[2]

        super(BftBaseTest, self).__init__()
        # Useful defaults
        self.reset_after_fail = True
        self.dont_retry = False
        self.logged = dict()
        self.subtests = []
        self.attempts = 0

        # initialize a step for teardown
        # TearDown step has a hook to call a fixture : teardown
        # this hook ensures that any action executed does not fail
        self.td_step = TearDown(
            self,
            "Excuting teardown for test: {}".format(self.__class__.__name__))

        # add a hook in class to call the fixture directly
        # need to ensure that self.call is used for teardown only
        self.__class__.call = self.td_step.call
        self.__class__.test_obj = self

    def id(self):
        return self.__class__.__name__

    def skipTest(self, reason):
        if _using_pytest:
            pytest.skip(reason)
        else:
            raise boardfarm.exceptions.SkipTest(reason)

    def startMarker(self):
        """Prints a banner at the beginning of a test, including the current time"""
        msg = "==================== Begin %s    Time: %s ====================" \
            % (self.__class__.__name__, now_short(self._format))

        lib.common.test_msg('\n' + msg)
        for c in self.dev.board.consoles:
            if hasattr(c.logfile_read, 'extra_log'):
                c.logfile_read.extra_log(msg)

    def endMarker(self):
        """Prints a banner at the end of a test, including test status, number of attempts (if applicable) and the current time"""
        result = self.result_grade
        if self.attempts:
            result = self.result_grade + "(" + str(self.attempts) + "/" + str(
                self.config.retry) + ")"
        msg = "==================== End %s   %s   Time: %s ==================" \
                    % (self.__class__.__name__, result, now_short(self._format))

        lib.common.test_msg('\n' + msg)
        for c in self.dev.board.consoles:
            if hasattr(c.logfile_read, 'extra_log'):
                c.logfile_read.extra_log(msg)

    def run(self, result=None):
        exc_to_raise = None
        self.startMarker()
        try:
            self.executionWrapper()
        except Exception as e:
            exc_to_raise = e

        if self.result_grade not in ["SKIP", "CC FAIL"]:
            try:
                func = getattr(self.__class__, "teardown_class", None)
                if func and not _using_pytest:
                    self.teardown_wrapper(func)
            except Exception as e:
                print(e)
                print("This should never happen. TearDown should be fail-safe")
                traceback.print_exc(file=sys.stdout)
                if type(exc_to_raise) is boardfarm.exceptions.BootFail:
                    raise exc_to_raise
                else:
                    raise
            finally:
                td = self.td_step
                if not td.td_result:
                    if 'FAIL' not in self.result_grade:
                        self.result_grade = "TD FAIL"
        else:
            self.endMarker()
            self.skipTest(self.result_grade)

        self.endMarker()

        if exc_to_raise:
            raise exc_to_raise

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

    def setup_wrapper(self, func):
        lib.common.test_msg(
            "\n==================== Running Setup %s    Time: %s ===================="
            % (self.__class__.__name__, now_short(self._format)))

        func()

    def teardown_wrapper(self, func):
        lib.common.test_msg(
            "\n==================== Running Teardown %s    Time: %s ===================="
            % (self.__class__.__name__, now_short(self._format)))

        func()

    def executionWrapper(self):
        self.start_time = time.time()
        recheck_devices = []

        for d in self.config.devices:
            dev = getattr(self.config, d)
            dev.test_to_log = self
            dev.test_prefix = d.encode("utf8")

        for c in self.dev.board.consoles:
            c.test_to_log = self
            c.test_prefix = 'console-%s' % str(
                self.dev.board.consoles.index(c) + 1)

            if not c.isalive():
                self.result_grade = "SKIP"
                print(
                    "\n\n=========== Test skipped! Board is not alive... ============="
                )
                self.skipTest("Board is not alive")
                raise

        try:
            if hasattr(self.dev, 'wan') and hasattr(self, 'wan_setup'):
                self.wan_setup()
            if hasattr(self.dev, 'lan') and hasattr(self, 'lan_setup'):
                self.lan_setup()
            if hasattr(self.dev, 'wlan') and hasattr(self, 'wlan_setup'):
                self.wlan_setup()

            if self.config.retry and not self.dont_retry:
                retry = self.config.retry
                self.attempts = 1
            else:
                self.attempts = retry = 0

            # TBC: should the setup and teardown part of the retry?
            func = getattr(self.__class__, "setup_class", None)
            if func and not _using_pytest:
                self.setup_wrapper(func)

            while retry >= 0:
                try:
                    # Pick function to run
                    if hasattr(self, "runTest"):
                        self.runTest()
                    elif hasattr(self, "test_main"):
                        self.test_main()
                    self.dev.board.touch()
                    break
                except boardfarm.exceptions.SkipTest:
                    raise
                except boardfarm.exceptions.ContingencyCheckError:
                    raise
                except Exception:
                    retry = retry - 1
                    if (retry > 0):
                        self.attempts = self.config.retry - retry + 1
                        traceback.print_exc(file=sys.stdout)
                        print(
                            "\n\n----------- Test failed! Retrying in 5 seconds... -------------"
                        )
                        debtcollector.deprecate(
                            "Using function/method 'recover()' is deprecated",
                            removal_version="> 1.1.1",
                            category=UserWarning)
                        self.recover()
                        time.sleep(5)
                        print(
                            "=========== Retry attempt number %s of %s ============="
                            % (self.attempts, self.config.retry))
                    else:
                        raise

            if hasattr(self.dev, 'wan') and hasattr(self, 'wan_cleanup'):
                self.wan_cleanup()
            if hasattr(self.dev, 'lan') and hasattr(self, 'lan_cleanup'):
                self.lan_cleanup()
            if hasattr(self.dev, 'wlan') and hasattr(self, 'wlan_cleanup'):
                self.wlan_cleanup()

            if hasattr(self, 'expected_failure') and self.expected_failure:
                self.result_grade = "Unexp OK"
            else:
                self.result_grade = "OK"

            self.stop_time = time.time()
            self.logged['test_time'] = float(self.stop_time - self.start_time)
        except boardfarm.exceptions.SkipTest as e:
            self.stop_time = time.time()
            self.logged['test_time'] = float(self.stop_time - self.start_time)
            self.result_grade = "SKIP"
            print("\n\nSkipping test: %s" % e)
            print("=========== Test skipped! Moving on... =============")
            return
        except boardfarm.exceptions.ContingencyCheckError as e:
            self.stop_time = time.time()
            self.logged['test_time'] = float(self.stop_time - self.start_time)
            self.result_grade = "CC FAIL"
            print("\n\nContingency check failed: %s" % e)
            print(
                "=========== Test skipped as contingency check failed! Moving on... ============="
            )
            return
        except Exception as e:
            self.stop_time = time.time()

            print(
                "\n\n=========== Test: %s failed! running Device status check! Time: %s ==========="
                % (self.__class__.__name__, now_short(self._format)))
            try:
                all_devices = [self.dev.board] + [
                    getattr(self.config, name, None)
                    for name in self.config.devices
                ]
                recheck_devices = check_devices(all_devices)
            except Exception as e:
                print(e)
            print(
                "\n\n=========== Test: %s failed! Device status check done! Time: %s ==========="
                % (self.__class__.__name__, now_short(self._format)))

            self.logged['test_time'] = float(self.stop_time - self.start_time)
            if hasattr(self, 'expected_failure') and self.expected_failure:
                self.result_grade = "Exp FAIL"
            else:
                self.result_grade = "FAIL"
            print(
                "\n\n=========== Test failed! Running recovery Time: %s ==========="
                % now_short(self._format))
            if e.__class__.__name__ == "TIMEOUT":
                print(e.get_trace())
            else:
                print(e)
                traceback.print_exc(file=sys.stdout)

            import os
            if 'BFT_DEBUG' in os.environ:
                print(self)
                for device in self.config.devices:
                    try:
                        d = getattr(self.config, device)
                        print(d)
                    except Exception:
                        traceback.print_exc(file=sys.stdout)

            debtcollector.deprecate(
                "Using function/method 'recover()' is deprecated",
                removal_version="> 1.1.1",
                category=UserWarning)

            try:
                self.recover()
                check_devices(recheck_devices)
            except Exception:
                print(
                    "These are maintenance functions, these should not throw an exception"
                )
                traceback.print_exc(file=sys.stdout)

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
        hosts = {}
        for device in self.config.devices:
            if re.search("wan|sip|phone", device):
                dev = getattr(self.config, device)
                if hasattr(dev, 'iface_dut'):
                    device_ip = dev.get_interface_ipaddr(dev.iface_dut)
                    hosts[str(device_ip)] = device + ".boardfarm.com"
        return hosts

    def execute_test_steps(self, prefix="", steps=[]):
        assert steps, "Please add steps to Test class before calling execute"
        for test_step in steps:
            if prefix:
                test_step.name = prefix + test_step.name
            with test_step:
                test_step.execute()
