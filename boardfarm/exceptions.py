class BftNotSupportedDevice(Exception):
    pass

class SkipTest(Exception):
    '''
    Raise this to skip running a test.
    '''
    pass
