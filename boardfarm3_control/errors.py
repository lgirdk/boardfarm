"""Control-plane errors that become structured HTTP responses."""

from __future__ import annotations

from http import HTTPStatus


class ControlError(Exception):
    """An error the control plane reports as ``{"detail": {"error": ..., ...}}``."""

    status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str, **fields: object) -> None:
        """Create the error.

        :param message: human-readable explanation
        :type message: str
        :param fields: extra machine-readable fields for the response detail
        :type fields: object
        """
        super().__init__(message)
        self.message = message
        self.fields = fields

    @property
    def code(self) -> str:
        """Return the machine-readable error name.

        :return: the class name, e.g. ``HostUnreachable``
        :rtype: str
        """
        return type(self).__name__

    def detail(self) -> dict[str, object]:
        """Build the response ``detail`` object.

        :return: error code, message and extra fields
        :rtype: dict[str, object]
        """
        return {"error": self.code, "message": self.message, **self.fields}


class BoardNotInInventory(ControlError):
    """The payload's inventory has no entry for the board being leased."""

    status = HTTPStatus.BAD_REQUEST


class UnknownMode(ControlError):
    """The session asks for a mode no installed plugin offers."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY


class NoHostForBoard(ControlError):
    """The inventory names no host for the board and no default host is set."""

    status = HTTPStatus.BAD_REQUEST


class UnknownHost(ControlError):
    """The board's ``agent_host`` names a host the registry does not know."""

    status = HTTPStatus.BAD_REQUEST


class HostDraining(ControlError):
    """The host refuses new sessions while it is drained for maintenance."""

    status = HTTPStatus.SERVICE_UNAVAILABLE


class HostUnreachable(ControlError):
    """The host's Docker daemon did not answer, or its breaker is open."""

    status = HTTPStatus.SERVICE_UNAVAILABLE


class ImagePullFailed(ControlError):
    """The host's daemon could not pull the agent image."""

    status = HTTPStatus.SERVICE_UNAVAILABLE


class BoardBusyOnHost(ControlError):
    """The board already has a running agent on its host."""

    status = HTTPStatus.CONFLICT


class BoardPendingStop(ControlError):
    """The board's previous agent could not be confirmed stopped yet."""

    status = HTTPStatus.CONFLICT


class HostInUse(ControlError):
    """The requested host change needs the host to have no sessions."""

    status = HTTPStatus.CONFLICT


class ManagedByControl(ControlError):
    """The call would change the agent's lifecycle behind the control plane's back."""

    status = HTTPStatus.FORBIDDEN


class SessionNotLive(ControlError):
    """The session has ended; its old agent port may belong to another agent now."""

    status = HTTPStatus.GONE


class StopPending(Exception):
    """A stop was requested but the session's host could not confirm it."""

    def __init__(self, session_id: str, host: str | None) -> None:
        """Record which session could not be confirmed stopped, and where.

        :param session_id: session whose stop is pending
        :type session_id: str
        :param host: host the session's agent runs on
        :type host: str | None
        """
        msg = f"stop of {session_id} on host {host} could not be confirmed"
        super().__init__(msg)
        self.session_id = session_id
        self.host = host
