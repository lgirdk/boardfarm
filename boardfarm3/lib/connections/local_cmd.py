"""Connect to a device with a local command."""


from typing import Any, Dict, List

from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


class LocalCmd(BoardfarmPexpect):
    """Connect to a device with a local command."""

    def __init__(
        self,  # pylint: disable=unused-argument
        name: str,
        conn_command: str,
        args: List[str] = None,
        **kwargs: Dict[str, Any],  # ignore other arguments
    ) -> None:
        """Initialize local command connection.

        :param conn_command: connection name
        :param args: arguments to the command, defaults to None
        """
        if args is None:
            args = []
        super().__init__(name, conn_command, args)

    def execute_command(self, command: str, timeout: int = -1) -> str:
        """Execute command in the local command session.

        :raises NotImplementedError: not supported in LocalCmd connection.
        """
        raise NotImplementedError(
            "LocalCmd connection doesn't support execute_command method. "
            "Please use other connection types which supports it."
        )
