from . import linux


class OpenEmbedded(linux.LinuxDevice):
    """OE core implementation extends LinuxDevice."""
    def install_package(self, pkg):
        """Install packages over OE.

        :param self: self object
        :type self: object
        :param pkg: package to be installed.
        :type pkg: string
        :raises: Exception Not implemented!
        """
        raise Exception("Not implemented!")
