import functools
import sys
import warnings

import pexpect
from boardfarm.exceptions import (BftDeprecate, ContOnFailError,
                                  PexpectErrorTimeout)
from boardfarm.lib.bft_logging import log_message
from debtcollector import removals

warnings.simplefilter("always", UserWarning)


@removals.remove(category=UserWarning)
def skip_on_fail(func):
    """If a test fails then it will throw a skipTest error."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        instance = args[0]
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_message(instance,
                        "skip_on_fail is deprecated method %s" % repr(e))
            raise BftDeprecate("skip_on_fail is deprecated method")

    return wrapper


def throw_pexpect_error(func):
    """If a pexpect.TIMEOUT occurs throw boardfarm.PexpectError error."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pexpect.TIMEOUT as e:
            raise PexpectErrorTimeout(e)

    return wrapper


# @pytest.fixture(scope="class")
def continue_on_fail(func):
    """Functions wrapped in continue_on_fail will not raise.

    an Exception in case of failure.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            exc = ContOnFailError(str(e))
            exc.tb = sys.exc_info()
            return exc

    return wrapper


def run_with_lock(lock):
    """Common thread function use for hardware critical functionalities."""
    def run_with_lock_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            lock.acquire()
            try:
                return func(*args, **kwargs)
            finally:
                lock.release()

        return wrapper

    return run_with_lock_decorator
