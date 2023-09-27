# !/usr/bin/python
import re


class iptable_parser:
    """
    Parse the iptables from table format to dict. output dict has keys of
    table chain and values of respective rules.
    """

    def __init__(self, *options):
        self.table_rule = {}
        self.chain_info = []

    def _get_header(self, ip_tables):
        for line in ip_tables.splitlines():
            if line.startswith("num"):
                self.header = line.split()
                break
        return self.header

    def iptables(self, ip_tables):
        """
        iptables meant for ipv4 only, get the iptable CLI output, parse and return as dict
        :param ip_tables: iptables output from DUT
        :return: dict of iptable
        """
        header = self._get_header(ip_tables)
        split_chain = re.split(r"Chain", ip_tables)
        self.key = None
        for i in range(len(split_chain)):
            rule_data = []
            for rule in split_chain[i].splitlines():
                rule_details = {}
                if re.match((r"\s[A-Za-z]"), rule):
                    self.key = rule.split(" ")[1]
                elif rule[:1].isdigit():
                    values = [entry for entry in rule.split()]
                    for cnt, val in enumerate(header[1 : len(header)], 1):
                        if val not in "opt":
                            rule_details[val] = values[cnt]
                    if len(values) > 10:
                        dest = " ".join(map(str, values[10 : len(values)]))
                        rule_details["to-target"] = dest
                    rule_data.append(rule_details)
            if self.key:
                self.table_rule[self.key] = rule_data
        assert self.table_rule, "Invalid table name or Table doesn't exist"
        return self.table_rule

    def ip6tables(self, ip6_tables):
        """
        ip6tables meant for ipv6 only, get the ip6tables CLI output, parse and return as dict
        :param ip_tables: iptables output from dut
        :return: dict of iptable
        """
        header = self._get_header(ip6_tables)
        header.remove("opt")
        split_chain = re.split(r"Chain", ip6_tables)
        self.key = None
        for i in range(len(split_chain)):
            rule_data = []
            for rule in split_chain[i].splitlines():
                rule_details = {}
                if re.match((r"\s[A-Za-z]"), rule):
                    self.key = rule.split(" ")[1]
                elif rule[:1].isdigit():
                    values = [entry for entry in rule.split()]
                    for cnt, val in enumerate(header[1 : len(header)], 1):
                        rule_details[val] = values[cnt]
                    if len(values) > 9:
                        dest = " ".join(map(str, values[9 : len(values)]))
                        rule_details["to-target"] = dest
                    rule_data.append(rule_details)
            if self.key:
                self.table_rule[self.key] = rule_data
        assert self.table_rule, "Invalid table name or Table doesn't exist"
        return self.table_rule

    def iptables_policy(self, ip_tables: str) -> dict[str, str]:
        """Return the iptables policy.

        :param ip_tables: output of iptables command
        :type ip_tables: str
        :return: dict of iptable policy
        :rtype: dict[str, str]
        """
        policy_dict = {}
        for policies in re.split(r"Chain", ip_tables):
            if len(lines := policies.strip().split("\n")) > 1:
                policy_key = lines[0].split()[0]
                policy_value = re.search(r"\((.*?)\)", lines[0])[1]
                policy_dict[policy_key] = policy_value
        return policy_dict
