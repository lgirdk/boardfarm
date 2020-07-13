#!/usr/bin/env python3

import unittest

import boardfarm


class TestSimpleBoardfarm(unittest.TestCase):
    def test_plugins_installed(self):
        """
        Verify some boardfarm plugins are installed.
        """
        self.assertGreater(len(boardfarm.plugins), 1)

    def test_import_testsuites(self):
        """
        Verify we can import testsuites and find
        a few needed testsuites.
        """
        from boardfarm import testsuites

        self.assertGreater(len(testsuites.list_tests), 5)
        self.assertIn("flash", testsuites.list_tests)
        self.assertIn("basic", testsuites.list_tests)
        self.assertIn("connect", testsuites.list_tests)

    def test_import_devices(self):
        """
        Verify we can import boardfarm devices.
        """
        import boardfarm.devices

        boardfarm.devices.probe_devices()
        self.assertGreater(len(boardfarm.devices.device_mappings), 10)


class TestSnmp(unittest.TestCase):
    def test_snmp_compile(self):
        """
        Verify the Simple Network Management Protocol (SNMP) helper
        functions successfully compile Management Information Base (mib)
        files.
        """
        tmp = boardfarm.lib.SnmpHelper.SnmpMibs.default_mibs
        self.assertGreater(len(tmp.mib_dict), 0)


if __name__ == "__main__":
    # Run all tests by typing one command:
    #     ./main.py -v
    unittest.main()
