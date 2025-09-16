"""nslookup command line utility output parser module."""

import re
from typing import Any

from boardfarm3.lib.regexlib import AllValidIpv6AddressesRegex, ValidIpv4AddressRegex


# pylint: disable=too-few-public-methods
class NslookupParser:
    """nslookup command line utility output parser module."""

    def parse_nslookup_output(self, response: str) -> dict[str, Any]:
        """Parse the DNS query response into dict obj.

        :param response: nslookup CLI output
        :type response: str
        :return: parsed nslookup output
        :rtype: Dict[str, str]
        """
        dns_dict_obj: dict[str, Any] = {}
        val = response.replace("\t\t", " ").replace("\t", " ")
        # pylint: disable-next=too-many-nested-blocks
        for i in val.split("\r\n\r\n"):
            if "Server" in i:
                for expr in [ValidIpv4AddressRegex, AllValidIpv6AddressesRegex]:
                    if re.search(expr, i):
                        matches = re.search(expr, i)[0]
                        break
                dns_dict_obj["dns_server"] = matches
            elif "Name" in i:
                dns_dict_obj["domain_name"] = re.search(r"(?:[\da-z\._]+)\.(\w+)", i)[0]
                ips: list[str] = []
                for value in [
                    ValidIpv4AddressRegex,
                    AllValidIpv6AddressesRegex,
                ]:
                    ips.extend(matches[0] for matches in re.finditer(value, i))
                dns_dict_obj["domain_ip_addr"] = ips
            elif "AAAA" in i:
                dns_dict_obj["domain_name"] = re.search(r"(?:[\da-z\.-]+)\.(\w+)", i)[0]
                dns_dict_obj["domain_ipv6_addr"] = re.findall(
                    AllValidIpv6AddressesRegex,
                    i,
                )
        assert dns_dict_obj, f"Error response: {response}"
        return dns_dict_obj
