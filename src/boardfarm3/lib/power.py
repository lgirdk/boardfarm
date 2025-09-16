"""Power module."""

from boardfarm3.devices.power.net_io import NetIOPDU
from boardfarm3.devices.power.raritan_pdu import RaritanPDU
from boardfarm3.templates.pdu import PDU

pdu_dict = {
    "px2://": RaritanPDU,
    "px3://": RaritanPDU,
    "netio://": NetIOPDU,
}


def get_pdu(uri: str) -> PDU:
    """Get a PDU object to drive the power of an outlet.

    Examples of pdu uris:
        "type://ip[:port]; outlet"

        "netio://10.64.40.34; 2"
        "px2://10.71.10.53:23; 2",
        "px3://10.71.10.53:23; 2",
        "eaton://10.71.10.53:23; 2"
        more to come....

    :param uri: a uri with the PDU details
    :type uri: str
    :raises ValueError: if the PDU URI is not recognised
    :return: a PDU templated object
    :rtype: PDU
    """
    for pdu_name, pdu_type in pdu_dict.items():
        if uri.startswith(pdu_name):
            return pdu_type(uri.replace(pdu_name, ""))
    msg = f"PDU uri: '{uri}' not recognised"
    raise ValueError(msg)
