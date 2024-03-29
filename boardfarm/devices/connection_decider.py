from . import (
    authenticated_serial_connections,
    kermit_connection,
    local_cmd,
    local_serial_connection,
    ser2net_connection,
    ssh_connection,
)


def connection(conn_type, device, **kwargs):
    """Return an object of the appropriate class type depending on the given connection type.

    Method initializes the connection specific parameters
    the connection type include ser2net, local_serial, ssh or kermit

    :param conn_type: indicates the conn_type to be used Ex : local_cmd, ser2net, local_serial, ssh, kermit_cmd
    :type conn_type: string
    :param device: the device to which connection to be established
    :type device: object
    :param ``**kwargs``: extra set of arguments to be used if any
    :type ``**kwargs``: dict
    :raises: NA
    :return: :class:`Response <Response>` object of class type used for connection
    :rtype: object
    """
    out = None
    if conn_type is None or conn_type == "local_cmd":
        out = local_cmd.LocalCmd(device=device, **kwargs)

    if conn_type == "ser2net":
        out = ser2net_connection.Ser2NetConnection(device=device, **kwargs)

    if conn_type == "local_serial":
        out = local_serial_connection.LocalSerialConnection(device=device, **kwargs)

    if conn_type == "ssh":
        out = ssh_connection.SshConnection(device=device, **kwargs)

    if conn_type == "kermit_cmd":
        out = kermit_connection.KermitConnection(device=device, **kwargs)

    if conn_type == "authenticated_telnet":
        out = authenticated_serial_connections.AuthenticatedTelnetConnection(
            device=device, **kwargs
        )

    if conn_type == "authenticated_ssh":
        out = authenticated_serial_connections.AuthenticatedSshConnection(
            device=device, **kwargs
        )

    if not out:
        # Default for all other models
        print(f"\nWARNING: Unknown connection type  '{type}'.")
        print(
            "Please check spelling, or write an appropriate class "
            "to handle that kind of board."
        )
        out = ser2net_connection.Ser2NetConnection(**kwargs)

    if hasattr(out, "close"):
        # We're assigning a bounded method of an instance to another instance from a different class.
        # The unbounded method cannot be accessed directly, hence pylint throws an error.
        unbound_method = out.close.__func__
        bounded_method = unbound_method.__get__(  # pylint: disable=E1111, E1120
            out.device, out.device.__class__
        )
        out.device.close = bounded_method

    return out
