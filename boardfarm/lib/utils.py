"""Boardfarm common utilities module."""

from netaddr import EUI, mac_unix_expanded


def get_nth_mac_address(mac_address: str, nth_number: int) -> str:
    """Get nth mac address from base mac address.

    :param mac_address: base mac address
    :param nth_number: n'th number from base mac address
    :returns: n'th mac address
    """
    return str(EUI(int(EUI(mac_address)) + nth_number, dialect=mac_unix_expanded))
