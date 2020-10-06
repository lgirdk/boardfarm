import abc


class NwUtilityStub:
    @abc.abstractmethod
    def netstat(self, opts="", extra_opts=""):
        raise Exception("Method not implemented")


class NwFirewallStub:
    @abc.abstractmethod
    def get_iptables_list(self, opts="", extra_opts=""):
        raise Exception("Method not implemented")

    @abc.abstractmethod
    def is_iptable_empty(self, opts="", extra_opts=""):
        raise Exception("Method not implemented")

    @abc.abstractmethod
    def get_ip6tables_list(self, opts="", extra_opts=""):
        raise Exception("Method not implemented")

    @abc.abstractmethod
    def is_ip6table_empty(self, opts="", extra_opts=""):
        raise Exception("Method not implemented")
