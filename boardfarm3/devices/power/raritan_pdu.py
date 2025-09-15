"""Raritan PDU module."""

import logging

from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    Integer,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    setCmd,
)

from boardfarm3.templates.pdu import PDU

_LOGGER = logging.getLogger(__name__)


class RaritanPDU(PDU):
    """Class contains methods to interact with Raritan PDU."""

    def __init__(self, uri: str) -> None:
        """Initialize Raritan PDU.

        The PDU is driven by SNMP commands.

        :param uri: uri as "ip;outlet"
        :type uri: str
        :raises ValueError: if an http port is provided
        """
        self._pdu_ip, self._outlet_id = uri.split(";")
        if ":" in self._pdu_ip:
            msg = f"RaritanPDU uses snmp, no port in {uri} allowed"
            raise ValueError(msg)

    def power_off(self) -> bool:
        """Power OFF the given PDU outlet.

        :returns: True on success
        """
        return self._perform_snmpset(0)

    def power_on(self) -> bool:
        """Power ON the given PDU outlet.

        :returns: True on success
        """
        return self._perform_snmpset(1)

    def power_cycle(self) -> bool:
        """Power cycle the given PDU outlet.

        :returns: True on success
        """
        return self._perform_snmpset(2)

    def _perform_snmpset(self, operation_id: int) -> bool:
        """Send snmp set command based on operation ID.

        :param operation_id: 0 (POWER OFF), 1 (POWER ON), 2 (POWER CYCLE)
        :type operation_id: int
        :returns: True on success
        """
        snmp_status = True
        oid = f".1.3.6.1.4.1.13742.6.4.1.2.1.2.1.{self._outlet_id}"
        (error_indication, error_status, _, _) = setCmd(
            SnmpEngine(),
            CommunityData("private"),
            UdpTransportTarget((self._pdu_ip, 161), timeout=10, retries=3),
            ContextData(),
            ObjectType(ObjectIdentity(oid), Integer(operation_id)),
        )
        if error_indication or error_status:
            error_msg = "Snmp command execution has failed"
            if error_indication:
                error_msg += f", {error_indication}"
            if error_status:
                error_msg += f", {error_status.prettyPrint()}"
            _LOGGER.error(error_msg)
            snmp_status = False
        return snmp_status
