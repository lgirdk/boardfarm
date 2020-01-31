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
        # unfortunately for now, we have to set the device manager
        # in boardfarm.devices before we can import tests.
        # Delete this part when tests no longer import from boardfarm.devices
        from boardfarm.lib import DeviceManager
        from boardfarm import devices
        devices.set_device_manager(DeviceManager.device_manager())
        from boardfarm import tests
        tests.init(None)
        # Also make sure something is in tests.available_tests
        self.assertGreater(len(tests.available_tests), 10)

    def test_import_testsuites(self):
        '''
        Verify we can import testsuites and find
        a few needed testsuites.
        '''
        from boardfarm import testsuites
        self.assertGreater(len(testsuites.list_tests), 5)
        self.assertIn('flash', testsuites.list_tests)
        self.assertIn('basic', testsuites.list_tests)
        self.assertIn('connect', testsuites.list_tests)

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

    def test_devicemanager(self):
        '''
        Verify we can add devices and get one back by type.
        '''
        from boardfarm.lib import DeviceManager
        class FakeDevice():
            def __init__(self, name):
                self.name = name
        dev1 = FakeDevice(name='board')
        dev2 = FakeDevice(name='lan')
        # Add devices to DeviceManager
        mgr = DeviceManager.device_manager()
        mgr._add_device(dev1)
        mgr._add_device(dev2)
        # Get a device back
        x = mgr.by_type(DeviceManager.device_type.lan)
        self.assertEqual('lan', x.name)
        # Get a device by the convience attribute
        y = mgr.lan
        self.assertEqual('lan', y.name)
        self.assertIn('board', dir(mgr))

    def test_board_filter(self):
        '''
        Verify regular-expression match filter for boards works.
        '''
        from boardfarm.lib import test_configurator
        # Fake station
        conf = {'type': 'raspberrypi', 'features': 'wifi'}
        # Should return true because it has 'wifi'
        result = test_configurator.filter_boards(conf, 'wifi')
        self.assertEqual(result, True)
        # Should return false because it doesn't have 'lasers'
        result = test_configurator.filter_boards(conf, 'lasers')
        self.assertEqual(result, False)

    def test_kibana_datagen(self):
        from boardfarm.library import generate_test_info_for_kibana
        class Dummy():
            logged = {}
            result_grade = 'OK'
        x = Dummy()
        x.override_kibana_name = "Testing123"
        nice_name, data = generate_test_info_for_kibana(x, prefix="Hello")
        self.assertEqual("HelloTesting123", nice_name)
        self.assertIn("HelloTesting123-result", data)

    def test_station_filtering(self):
        from boardfarm.lib import test_configurator
        cur_dir = os.path.dirname(boardfarm.__file__)
        loc, conf = test_configurator.get_station_config(os.path.join(cur_dir, 'boardfarm_config_example.json'))
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
