"""Connection decider module."""


from typing import Any

from boardfarm.exceptions import EnvConfigError
from boardfarm.lib.boardfarm_pexpect import BoardfarmPexpect
from boardfarm.lib.connections.ldap_authenticated_serial import LdapAuthenticatedSerial
from boardfarm.lib.connections.ssh_connection import SSHConnection


def connection_factory(
    connection_type: str, connection_name: str, **kwargs: Any
) -> BoardfarmPexpect:
    """Return connection of given type.

    :param connection_type: type of the connection
    :param connection_name: name of the connection
    :param kwargs: arguments to the connection
    :returns: BoardfarmPexpect: connection of given type
    :raises EnvConfigError: when given connection type is not supported
    """
    connection_dispatcher = {
        "ssh_connection": SSHConnection,
        "authenticated_ssh": SSHConnection,
        "ldap_authenticated_serial": LdapAuthenticatedSerial,
    }
    if connection_type not in connection_dispatcher:
        raise EnvConfigError(f"Unsupported connection type: {connection_type}")
    if connection_type == "ssh_connection":
        kwargs.pop("password")
    return connection_dispatcher[connection_type](connection_name, **kwargs)
