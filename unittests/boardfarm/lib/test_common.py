#!/usr/bin/env python
"""Unit tests for boardfarm.lib.common.py."""
import pytest
from boardfarm.lib import common


def prt_smt(data):
    """Print something, in function format, to avoid pyflakes issues."""
    print(data)


def throw_error():
    """Simple, common, function to throw an Error."""
    raise NameError


class TestRetryOnException:
    """Suite of tests for boardfarm.lib.common.retry_on_exception()."""

    def test_retry_on_exception_no_raise_no_retry(self):
        """A proper function call does not trigger any exception."""
        out = common.retry_on_exception(sum, [(3, 2)], 0, tout=0)
        assert out == 5

    def test_retry_on_exception_no_raise_1_retry(self):
        """A proper function call does not trigger any exception."""
        out = common.retry_on_exception(sum, [(3, 2)], 1, tout=0)
        assert out == 5

    def test_retry_on_exception_no_output(self):
        """A proper function call does not trigger any exception."""
        print_var = ["you should read this line only once"]
        out = common.retry_on_exception(prt_smt, print_var, 1, tout=0)
        assert out is None

    @pytest.mark.parametrize("test_input", [0, 3])
    def test_retry_with_exceptions(self, test_input):
        """The exception is raised after a given number of retries."""
        with pytest.raises(NameError):
            common.retry_on_exception(throw_error, (), test_input, tout=0)

    def test_retry_with_exception_default(self):
        """The exception is raised when no retries are specified."""
        with pytest.raises(NameError):
            common.retry_on_exception(throw_error, (), tout=0)

    def test_retry_on_exception_neg_retry(self):
        """The exception is raised when no retries are specified."""
        with pytest.raises(NameError):
            common.retry_on_exception(throw_error, (), -1, tout=0)
