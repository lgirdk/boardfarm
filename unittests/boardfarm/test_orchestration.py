import pytest
from boardfarm.orchestration import TestStep as TS
from boardfarm.tests.bft_base_test import BftBaseTest
from unittest2 import TestCase


# Assumption1 : later test won't define runTest
# Assumption2 : BF pytest pluging won't call a wrapper to execute runTest
# Assumption3 : BF pytest will directly used test prefixed methods
class BfPyTestCls(TestCase, BftBaseTest):
    def __init__(self, *args, **kwargs):
        # This is just to ensure the pytest runs with BF
        # this is done so that base prefixed/suffixed test method don't run
        TestCase.__init__(self, *args, **kwargs)
        BftBaseTest.__init__(self, None, None, None)


class test_orchestration(BfPyTestCls):

    # this will always raise a ValueError exception
    def action(self, code=200):
        e = ValueError("Intended Exception")
        e.code = code
        raise e

    def test_positive_scenario1(self):
        with TS(self, "Negative Test Scenario 1", type(self).__name__) as ts:
            with ts.assertRaises(ValueError) as e:
                ts.call(self.action)
            exc = e.exception
            assert exc.code == 200

    def test_positive_scenario2(self):
        with TS(self, "Negative Test Scenario 2", type(self).__name__) as ts:
            exc = ts.assertRaises(ValueError, self.action, code=300).exception
            assert exc.code == 300

    def test_positive_scenario3(self):
        # should be able to continue remaining execution after with, if any.
        with TS(self, "Negative Test Scenario 3", type(self).__name__) as ts:
            with ts.assertRaises(ValueError) as e:
                ts.call(self.action)
            ts.call(print, "Yes I work")
            exc = e.exception
            assert exc.code == 200

    def test_positive_scenario4(self):
        # should be able to continue remaining execution after with, if any.
        with TS(self, "Negative Test Scenario 4", type(self).__name__) as ts:
            exc = ts.assertRaises(ValueError, self.action, code=300).exception
            ts.call(print, "Yes I work")
            assert exc.code == 300

    def test_negative_scenario1(self):
        # this scenario will throw an exception Code Error
        with pytest.raises(AssertionError) as exc:
            with TS(self, "Negative Test Scenario 5",
                    type(self).__name__) as ts:
                with ts.assertRaises(KeyError):
                    ts.call(self.action)
        assert exc.type is AssertionError

    def test_negative_scenario2(self):
        # this scenario will throw an exception Code Error
        with pytest.raises(AssertionError) as exc:
            with TS(self, "Negative Test Scenario 6",
                    type(self).__name__) as ts:
                ts.assertRaises(KeyError, self.action, code=100)
        assert exc.type is AssertionError

    def test_negative_scenario3(self):
        # this scenario will throw an exception Code Error as no exception got raised
        with pytest.raises(AssertionError) as exc:
            with TS(self, "Negative Test Scenario 7",
                    type(self).__name__) as ts:
                with ts.assertRaises(KeyError):
                    ts.call(print, "I won't throw an exception")
        assert "No exception caught" in str(exc.value)

    def test_negative_scenario4(self):
        # this scenario will throw an exception Code Error as no exception got raised
        with pytest.raises(AssertionError) as exc:
            with TS(self, "Negative Test Scenario 8",
                    type(self).__name__) as ts:
                ts.assertRaises(KeyError, print, "I won't throw an exception")
        assert "No exception caught" in str(exc.value)
