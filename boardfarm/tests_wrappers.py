import functools
from boardfarm.lib.bft_logging import log_message
from boardfarm.exceptions import PexpectErrorTimeout
import pexpect

def skip_on_fail(func):
    """If a test fails then it will throw a skipTest error"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        instance = args[0]
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_message(instance, "Skipping Test : %s" % repr(e))
            instance.skipTest(e)
    return wrapper

def throw_pexpect_error(func):
    """If a pexpect.TIMEOUT occurs throw boardfarm.PexpectError error"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pexpect.TIMEOUT as e:
            raise PexpectErrorTimeout(e)
    return wrapper


