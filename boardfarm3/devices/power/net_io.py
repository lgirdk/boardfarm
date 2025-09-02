# ruff: noqa: S105

"""NetIO PDU module."""

import logging

import httpx

from boardfarm3.templates.pdu import PDU

_LOGGER = logging.getLogger(__name__)


class NetIOPDU(PDU):
    """Class contains methods to interact with NetIO PDU."""

    def __init__(self, uri: str) -> None:
        """Initialize NetIO PDU instance.

        The PDU is driven via the URL[sic] API as defined is the manual.

        :param uri: uri as "ip[:port];outlet"
        :type uri: str
        """
        ip_port, outlet = uri.split(";")
        ip_addr = ip_port.split(":")[0]
        port = f":{ip_port.split(':')[1]}" if ":" in ip_port else ""
        self._url = f"http://{ip_addr}{port}/netio.cgi"
        self._outlet = f"output{outlet.strip()}"
        self._pass = "bigfoot1"

    def power_off(self) -> bool:
        """Power OFF the given PDU outlet.

        :returns: True on success
        :rtype: bool
        """
        return self._perform_get("0")

    def power_on(self) -> bool:
        """Power ON the given PDU outlet.

        :returns: True on success
        :rtype: bool
        """
        return self._perform_get("1")

    def power_cycle(self) -> bool:
        """Power cycle the given PDU outlet.

        :returns: True on success
        :rtype: bool
        """
        return self._perform_get("2")

    def _perform_get(self, operation: str) -> bool:
        """Perform web action on the outlet.

        :param operation: 0 (POWER OFF), 1 (POWER ON), 2 (POWER CYCLE)
        :type operation: str
        :returns: True on httpx.get(...).text == "OK"
        :rtype: bool
        """
        _params = {"pass=": self._pass, self._outlet: operation}
        _LOGGER.debug("PDU: %s %s", self._url, _params)
        res = httpx.get(self._url, params=_params)  # pylint: disable=E1123
        res.raise_for_status()
        return res.text == "OK"
