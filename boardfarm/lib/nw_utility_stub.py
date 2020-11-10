import abc


class NwUtilityStub:
    @abc.abstractmethod
    def netstat(self, opts="", extra_opts=""):
        raise NotImplementedError


class NwFirewallStub:
    @abc.abstractmethod
    def get_iptables_list(self, opts="", extra_opts=""):
        raise NotImplementedError

    @abc.abstractmethod
    def is_iptable_empty(self, opts="", extra_opts=""):
        raise NotImplementedError

    @abc.abstractmethod
    def get_ip6tables_list(self, opts="", extra_opts=""):
        raise NotImplementedError

    @abc.abstractmethod
    def is_ip6table_empty(self, opts="", extra_opts=""):
        raise NotImplementedError

    @abc.abstractmethod
    def add_drop_rule_iptables(self, option, valid_ip):
        raise NotImplementedError

    @abc.abstractmethod
    def add_drop_rule_ip6tables(self, option, valid_ip):
        raise NotImplementedError

    @abc.abstractmethod
    def del_drop_rule_iptables(self, option, valid_ip):
        raise NotImplementedError

    @abc.abstractmethod
    def del_drop_rule_ip6tables(self, option, valid_ip):
        raise NotImplementedError


class NwDnsLookupStub:
    @abc.abstractmethod
    def nslookup(self, domain_name, opts="", extra_opts=""):
        raise NotImplementedError


class DHCPStub:
    class DHCPClientStub:
        @abc.abstractmethod
        def dhclient(self, interface, opts="", extra_opts=""):
            raise NotImplementedError
