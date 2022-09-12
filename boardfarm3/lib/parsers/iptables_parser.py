"""Parser module for iptables command output."""

import re
from typing import Dict, List

# TODO: Rewrite this library in a better way


class IptablesParser:
    """Parse the iptables from table format to dict."""

    def _get_headers(self, ip_tables: str) -> List[str]:
        for line in ip_tables.splitlines():
            if line.startswith("num"):
                header = line.split()
                break
        return header

    def iptables(self, ip_tables: str) -> Dict[str, List[Dict]]:
        """Return parsed given iptables output.

        :param ip_tables: iptables command output
        :type ip_tables: str
        :return: parsed iptables output in dictionary
        :rtype: Dict[str, List[Dict]]
        """
        headers = self._get_headers(ip_tables)
        split_chain = re.split("Chain", ip_tables)
        key = None
        table_rule: Dict[str, List[Dict]] = {}
        # pylint: disable=too-many-nested-blocks, consider-using-enumerate
        for i in range(len(split_chain)):
            rule_data: List[Dict] = []
            for rule in split_chain[i].splitlines():
                rule_details = {}
                if re.match(r"\s[A-Za-z]", rule):
                    key = rule.split(" ")[1]
                elif rule[:1].isdigit():
                    values = list(rule.split())
                    for cnt, val in enumerate(headers[1:], 1):
                        if val not in "opt":
                            rule_details[val] = values[cnt]
                    if len(values) > 10:
                        dest = " ".join(map(str, values[10:]))
                        rule_details["to-target"] = dest
                    rule_data.append(rule_details)
            if key:
                table_rule[key] = rule_data
        assert table_rule, "Invalid table name or Table doesn't exist"
        return table_rule

    def ip6tables(self, ip6_tables: str) -> Dict[str, List[Dict]]:
        """Return parsed given ip6tables output.

        :param ip_tables: ip6tables command output
        :type ip_tables: str
        :return: parsed ip6tables output in dictionary
        :rtype: Dict[str, List[Dict]]
        """
        header = self._get_headers(ip6_tables)
        header.remove("opt")
        split_chain = re.split("Chain", ip6_tables)
        key = None
        table_rule: Dict[str, List[Dict]] = {}
        # pylint: disable=too-many-nested-blocks, consider-using-enumerate
        for i in range(len(split_chain)):
            rule_data = []
            for rule in split_chain[i].splitlines():
                rule_details = {}
                if re.match(r"\s[A-Za-z]", rule):
                    key = rule.split(" ")[1]
                elif rule[:1].isdigit():
                    values = list(rule.split())
                    for cnt, val in enumerate(header[1:], 1):
                        rule_details[val] = values[cnt]
                    if len(values) > 9:
                        dest = " ".join(map(str, values[9:]))
                        rule_details["to-target"] = dest
                    rule_data.append(rule_details)
            if key:
                table_rule[key] = rule_data
        assert table_rule, "Invalid table name or Table doesn't exist"
        return table_rule
