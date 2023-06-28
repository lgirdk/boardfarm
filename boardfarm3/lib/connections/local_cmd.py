"""Connect to a device with a local command."""


from typing import Any

from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class LocalCmd(BoardfarmPexpect):
    """Connect to a device with a local command."""

    def __init__(
        self,  # pylint: disable=unused-argument
        name: str,
        conn_command: str,
        save_console_logs: bool,
        args: list[str] = None,
        **kwargs: dict[str, Any],  # ignore other arguments  # noqa: ARG002
    ) -> None:
        """Initialize local command connection.

        :param name: connection name
        :type name: str
        :param conn_command: command to start the session
        :type conn_command: str
        :param save_console_logs: save console logs to disk
        :type save_console_logs: bool
        :param args: arguments to the command, defaults to None
        :type args: list[str], optional
        :param kwargs: additional keyword args
        """
        if args is None:
            args = []
        super().__init__(name, conn_command, save_console_logs, args)

    def execute_command(self, command: str, timeout: int = -1) -> str:  # noqa: ARG002
        """Execute command in the local command session.

        :param command: command to be executed
        :param timeout: timeout
        :raises NotImplementedError: not supported in LocalCmd connection.
        """
        msg = (
            "LocalCmd connection does not support execute_command method. "
            "Please use other connection types which supports it."
        )
        raise NotImplementedError(
            msg,
        )
