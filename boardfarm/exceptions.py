import pexpect


class BftBaseException(Exception):
    """Base exception all Bft exceptions inherit from
    """


class TestError(BftBaseException):
    """Raise this if a TestStep verification fails.
    Each test step in boardfarm.orchestration verifies the output of its execution and throws a TestError exception on False"
    """
    pass


class TestImportError(Exception):
    '''
    Raise this if there is an exception when importing a test.
    '''
    pass


class BftNotSupportedDevice(BftBaseException):
    """Raise this if a device is blocked but not used.
    """
    pass


class SkipTest(BftBaseException):
    """Raise this to skip running a test.
    """
    pass


class BootFail(BftBaseException):
    """Raise this if the board fails to boot.
    This exception is special because if it
    occurs then most likely no other test
    can successfully run.
    """
    pass


class CodeError(BftBaseException):
    """Raise this if an code assert fails
    This exception is only meant for custom assert
    clause used inside libraries.
    Not to be used with TestStep verification.
    """
    pass


class PexpectErrorTimeout(pexpect.TIMEOUT, BftBaseException):
    """Raise this if pexpect times out
    """
    pass


class ConfigKeyError(BftBaseException):
    """Invalid use of key in config object
    """
    pass


class DeviceDoesNotExistError(BftBaseException):
    """Device does not exist
    """
    pass


class BftEnvException(BftBaseException):
    """Generic for Env related problems"""
    pass


class BftEnvExcKeyError(BftEnvException):
    """Env error raised when a key is missing from ENV"""
    pass


class BftEnvMismatch(BftEnvException):
    """Raised when an env value is wrong for a particular key"""
    pass


class BFTypeError(BftBaseException):
    """Raise this if an invalid data type is passed"""
    pass


class ConnectionRefused(BftBaseException):
    """Raise this exception when we fail to ssh/telnet to a machine"""
    pass


class ContingencyCheckError(BftBaseException):
    """Raise this exception when a contingency check fails after env check.
    The contingency checks occurs at beginning of each test.
    """
    pass


class ACSFaultCode(BftBaseException):
    """Raise this exception when ACS/CPE sends a fault code.
    """
    pass


class ContOnFailError(BftBaseException):
    """Use this exception when a step fails to execute for continue_on_fail.
    This exceptions is used along with a fixture to mark tests as FAIL
    """
    pass


class NoTFTPServer(BftBaseException):
    """Raise this exception when no TFTP server is found, but we need one."""
    pass
