import abc


class NwUtilityStub:
    @abc.abstractmethod
    def netstat(self, opts="", extra_opts=""):
        raise Exception("Method not implemented")
