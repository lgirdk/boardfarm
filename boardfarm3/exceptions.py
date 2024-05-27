"""Boardfarm exceptions for all plugins and modules used by framework."""

from typing import Any


class BoardfarmException(Exception):
    """Base exception all boardfarm exceptions inherit from."""


class DeviceConnectionError(BoardfarmException):
    """Raise this on device connection error."""


class SSHConnectionError(DeviceConnectionError):
    """Raise this on SSH connection failure."""


class SCPConnectionError(DeviceConnectionError):
    """Raise this on SCP connection failure."""


class EnvConfigError(BoardfarmException):
    """Raise this on environment configuration error."""


class DeviceRequirementError(BoardfarmException):
    """Raise this on device requirement error."""


class DeviceNotFound(BoardfarmException):
    """Raise this on device is not available."""


class FileLockTimeout(BoardfarmException):
    """Raise this on file lock timeout."""


class ConfigurationFailure(BoardfarmException):
    """Raise this on device configuration failure."""


class DeviceBootFailure(BoardfarmException):
    """Raise this on device boot failure."""


class TR069ResponseError(BoardfarmException):
    """Raise this on TR069 response error."""


class TR069FaultCode(BoardfarmException):
    """Raise this on TR069 response error."""

    faultdict: dict[str, Any]


class UseCaseFailure(BoardfarmException):
    """Raise this on failures in use cases."""


class NotSupportedError(BoardfarmException):
    """Raise this on feature not supported."""


class SNMPError(BoardfarmException):
    """Raise this on any SNMP related error."""


class VoiceError(BoardfarmException):
    """Raise this on any voice related errors."""


# TODO: maybe move to testsuite
class TeardownError(BoardfarmException):
    """Raise this on any test teardown failure."""


class ContingencyCheckError(BoardfarmException):
    """Raise this on any contingency check failure."""


class WifiError(BoardfarmException):
    """Raise this on any wifi related errors."""


class MulticastError(BoardfarmException):
    """Raise this on any multicast related errors."""


class CodeError(BoardfarmException):
    """Raise this if an code assert fails.

    This exception is only meant for custom assert
    clause used inside libraries.
    """
