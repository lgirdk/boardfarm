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
