# !/usr/bin/python
import re

from .regexlib import AllValidIpv6AddressesRegex, ValidIpv4AddressRegex


class DnsParser(object):
    """
    nslookup is a network admin CLI available in many OS for querying the
    Domain Name System to obtain domain name or IP address mapping,
    This parser helps to get the nslookup output and perform parsing action.
    """

    def __init__(self, *options):
        """"""
        self.dns_dict_obj = {}

    def parse_nslookup_output(self, response):
        """
        Method to parse the DNS query response into dict obj.
        :param response: nslookup CLI output
        :type response: str
        :return: dict obj
        """
        val = response.replace("\t\t", " ").replace("\t", " ")
        for i in val.split("\r\n\r\n"):
            if "Server" in i:
                self.dns_dict_obj["dns_server"] = re.search(
                    ValidIpv4AddressRegex, i
                ).group(0)
            elif "Name" in i:
                self.dns_dict_obj["domain_name"] = re.search(
                    r"(?:[\da-z\.-]+)\.(\w+)", i
                ).group(0)
                ips = []
                for value in [ValidIpv4AddressRegex, AllValidIpv6AddressesRegex]:
                    for match in re.finditer(value, i):
                        ips.append(match.group(0))
                self.dns_dict_obj["domain_ip_addr"] = ips
            elif "AAAA" in i:
                self.dns_dict_obj["domain_name"] = re.search(
                    r"(?:[\da-z\.-]+)\.(\w+)", i
                ).group(0)
                self.dns_dict_obj["domain_ipv6_addr"] = re.findall(
                    AllValidIpv6AddressesRegex, i
                )
        assert self.dns_dict_obj, f"Error response: {response}"
        return self.dns_dict_obj
