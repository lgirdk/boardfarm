import pytest
from boardfarm.orchestration import TestStep as TS


class Test(object):
    """Sample Test class."""

    steps = []
    log_to_file = None
    dev = None

    # this will always raise a ValueError exception
    def action(self, code=200):
        e = ValueError("Intended Exception")
        e.code = code
        raise e


@pytest.fixture(scope="module")
def obj():
    yield Test()


def test_positive_scenario1(obj):
    with TS(obj, "Negative Test Scenario 1", type(obj).__name__) as ts:
        with ts.assertRaises(ValueError) as e:
            ts.call(obj.action)
        exc = e.exception
        assert exc.code == 200


def test_positive_scenario2(obj):
    with TS(obj, "Negative Test Scenario 2", type(obj).__name__) as ts:
        exc = ts.assertRaises(ValueError, obj.action, code=300).exception
        assert exc.code == 300


def test_positive_scenario3(obj):
    # should be able to continue remaining execution after with, if any.
    with TS(obj, "Negative Test Scenario 3", type(obj).__name__) as ts:
        with ts.assertRaises(ValueError) as e:
            ts.call(obj.action)
        ts.call(print, "Yes I work")
        exc = e.exception
        assert exc.code == 200


def test_positive_scenario4(obj):
    # should be able to continue remaining execution after with, if any.
    with TS(obj, "Negative Test Scenario 4", type(obj).__name__) as ts:
        exc = ts.assertRaises(ValueError, obj.action, code=300).exception
        ts.call(print, "Yes I work")
        assert exc.code == 300


def test_negative_scenario1(obj):
    # this scenario will throw an exception Code Error
    with pytest.raises(AssertionError) as exc:
        with TS(obj, "Negative Test Scenario 5", type(obj).__name__) as ts:
            with ts.assertRaises(KeyError):
                ts.call(obj.action)
    assert exc.type is AssertionError


def test_negative_scenario2(obj):
    # this scenario will throw an exception Code Error
    with pytest.raises(AssertionError) as exc:
        with TS(obj, "Negative Test Scenario 6", type(obj).__name__) as ts:
            ts.assertRaises(KeyError, obj.action, code=100)
    assert exc.type is AssertionError


def test_negative_scenario3(obj):
    # this scenario will throw an exception Code Error as no exception got raised
    with pytest.raises(AssertionError) as exc:
        with TS(obj, "Negative Test Scenario 7", type(obj).__name__) as ts:
            with ts.assertRaises(KeyError):
                ts.call(print, "I won't throw an exception")
    assert "No exception caught" in str(exc.value)


def test_negative_scenario4(obj):
    # this scenario will throw an exception Code Error as no exception got raised
    with pytest.raises(AssertionError) as exc:
        with TS(obj, "Negative Test Scenario 8", type(obj).__name__) as ts:
            ts.assertRaises(KeyError, print, "I won't throw an exception")
    assert "No exception caught" in str(exc.value)
