class TestError(Exception):
    """
    Raise this if a TestStep verification fails
    """
    pass

class BftNotSupportedDevice(Exception):
    pass

class SkipTest(Exception):
    '''
    Raise this to skip running a test.
    '''
    pass

class BootFail(Exception):
    '''
    Raise this if the board fails to boot.
    This exception is special because if it
    occurs then most likely no other test
    can successfully run.
    '''
    pass

class CodeError(Exception):
    """Raise this if an code assert fails

    This exception is only meant for custom assert
    clause used inside libraries.
    Not to be used with TestStep verification.
    """
    pass

class PexpectError(Exception):
    """
    Raise this if pexpect times out
    """
    pass
