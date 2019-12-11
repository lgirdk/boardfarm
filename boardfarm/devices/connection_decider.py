from . import ser2net_connection
from . import local_serial_connection
from . import ssh_connection
from . import local_cmd
from . import kermit_connection

def connection(conn_type, device, **kwargs):
    """This method return an object of the appropriate class type depending on the given connection type
    Method initializes the connection specific parameters
    the connection type include ser2net, local_serial, ssh or kermit

    :param conn_type: indicates the conn_type to be used Ex : local_cmd, ser2net, local_serial, ssh, kermit_cmd
    :type conn_type: string
    :param device: the device to which connection to be established
    :type device: object
    :param **kwargs: extra set of arguements to be used if any
    :type **kwargs: dict
    :raises: NA
    :return: :class:`Response <Response>` object of class type used for connection
    :rtype: object
    """
    if conn_type is None or conn_type in ("local_cmd"):
        return local_cmd.LocalCmd(device=device, **kwargs)

    if conn_type in ("ser2net"):
        return ser2net_connection.Ser2NetConnection(device=device, **kwargs)

    if conn_type in ("local_serial"):
        return local_serial_connection.LocalSerialConnection(device=device, **kwargs)

    if conn_type in ("ssh"):
        return ssh_connection.SshConnection(device=device, **kwargs)

    if conn_type in ("kermit_cmd"):
        return kermit_connection.KermitConnection(device=device, **kwargs)

    # Default for all other models
    print("\nWARNING: Unknown connection type  '%s'." % type)
    print("Please check spelling, or write an appropriate class "
          "to handle that kind of board.")
    return ser2net_connection.Ser2NetConnection(**kwargs)
