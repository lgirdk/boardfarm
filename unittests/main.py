#!/usr/bin/env python3

import boardfarm
import os
import unittest

class TestSimpleBoardfarm(unittest.TestCase):

    def test_plugins_installed(self):
        '''
        Verify some boardfarm plugins are installed.
        '''
        self.assertGreater(len(boardfarm.plugins), 1)

    def test_import_tests(self):
        '''
        Verify we can import all boardfarm tests.
        '''
        from boardfarm import tests
        tests.init(None)

    def test_import_debian_wifi(self):
        '''
        Verify we can import a specific device by name.
        '''
        import boardfarm.devices.debian_wifi

    def test_import_devices(self):
        '''
        Verify we can import boardfarm devices.
        '''
        import boardfarm.devices
        boardfarm.devices.probe_devices()
        self.assertGreater(len(boardfarm.devices.device_mappings), 10)

    def test_station_filtering(self):
        from boardfarm.lib import test_configurator
        cur_dir = os.path.dirname(boardfarm.__file__)
        conf = test_configurator.get_station_config(os.path.join(cur_dir, 'boardfarm_config_example.json'))
        names = test_configurator.filter_station_config(conf,
                                                        board_type=["qemux86"])
        self.assertGreater(len(names), 0)
        names = test_configurator.filter_station_config(conf,
                                                        board_type=["qemux86"],
                                                        board_filter="local")
        self.assertGreater(len(names), 0)

class TestSnmp(unittest.TestCase):

    def test_snmp_compile(self):
        '''
        Verify the Simple Network Management Protocol (SNMP) helper
        functions successfully compile Management Information Base (mib)
        files.
        '''
        tmp = boardfarm.lib.SnmpHelper.SnmpMibs.default_mibs
        self.assertGreater(len(tmp.mib_dict), 0)


if __name__ == '__main__':
    # Run all tests by typing one command:
    #     ./main.py -v
    unittest.main()
