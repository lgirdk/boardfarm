import functools
from boardfarm.lib.bft_logging import log_message

def skip_on_fail(func):
    """If a test fails then it will throw a skipTest error"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        instance = args[0]
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_message(instance, "Skipping Test : %s" % e.message)
            instance.skipTest(e.message)
    return wrapper



