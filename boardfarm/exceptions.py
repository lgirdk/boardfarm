"""Boardfarm exceptions for all plugins and modules used by framework."""


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
