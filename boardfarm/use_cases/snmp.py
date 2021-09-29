"""SNMP use cases library."""
from typing import Dict, Tuple, Union

from boardfarm.lib.DeviceManager import get_device_by_name
from boardfarm.lib.SNMPv2 import SNMPv2


def snmp_get(
    mib_name: str,
    index: int = 0,
    community: str = "private",
    extra_args: str = "",
    timeout: int = 10,
    retries: int = 3,
) -> Tuple[str, str, str]:
    """SNMP GET board MIB from wan device via SNMPv2

    :param mib_name: MIB name. Will be searched in loaded MIB libraries.
    :param index: MIB index, default to 0
    :param community: public/private(default)
    :param extra_args: see man snmpget for extra args
    :param timeout: seconds, 10 by default
    :param retries: 3 by default
    :return: value, type, full snmp output
    :raise SNMPError: if value is not found in output (e.g. .1.3.6.1.2.1.69.1.3.2.0 = "")
                      if MIB is not found in loaded MIBs
    """
    wan = get_device_by_name("wan")
    board = get_device_by_name("board")
    cmts = get_device_by_name("cmts")
    return SNMPv2(wan, cmts.get_cmip(board.cm_mac)).snmpget(
        mib_name, index, community, extra_args, timeout, retries
    )


def snmp_set(
    mib_name: str,
    value: str,
    stype: str,
    index: int = 0,
    community: str = "private",
    extra_args: str = "",
    timeout: int = 10,
    retries: int = 3,
) -> Tuple[str, str, str]:
    """SNMP SET board MIB from wan device via SNMPv2

    :param mib_name: MIB name. Will be searched in loaded MIB libraries.
    :param value: value to be set.
    :param stype: defines the datatype of value to be set for mib_name.
                  One of i, u, t, a, o, s, x, d, b.
                  i: INTEGER, u: unsigned INTEGER, t: TIMETICKS, a: IPADDRESS
                  o: OBJID, s: STRING, x: HEX STRING, d: DECIMAL STRING, b: BITS
                  U: unsigned int64, I: signed int64, F: float, D: double
    :param index: MIB index, default to 0.
    :param community: public/private(default).
    :param extra_args: see man snmpset for extra args.
    :param timeout: seconds, 10 by default.
    :param retries: 3 by default.
    :return: value, type, full snmp output
    :raise SNMPError: if MIB is not found in loaded MIBs
    :raise AssertionError: in case snmpset output doesn't contain value (failed to set value)
    """
    wan = get_device_by_name("wan")
    board = get_device_by_name("board")
    cmts = get_device_by_name("cmts")
    return SNMPv2(wan, cmts.get_cmip(board.cm_mac)).snmpset(
        mib_name, value, stype, index, community, extra_args, timeout, retries
    )


def snmp_walk(
    mib_name: str,
    index: Union[int, str, None] = 0,
    community: str = "private",
    extra_args: str = "",
    timeout: int = 10,
    retries: int = 3,
) -> Tuple[Dict[str, Tuple[str, str]], str]:
    """SNMP WALK board MIB from wan device via SNMPv2

    :param mib_name: MIB name. Will be searched in loaded MIB libraries.
    :param index: MIB index, default to 0
    :param community: public/private(default)
    :param extra_args: see man snmpwalk for extra args
    :param timeout: seconds, 10 by default
    :param retries: 3 by default
    :return: (dictionary of mib_oid as key and tuple(mib value, mib type) as value, complete output)
    :raise SNMPError: if value is not found in output (e.g. .1.3.6.1.2.1.69.1.3.2.0 = "")
                      if MIB is not found in loaded MIBs
    """
    wan = get_device_by_name("wan")
    board = get_device_by_name("board")
    cmts = get_device_by_name("cmts")
    return SNMPv2(wan, cmts.get_cmip(board.cm_mac)).snmpwalk(
        mib_name, index, community, retries, timeout, extra_args
    )
