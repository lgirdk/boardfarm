"""Provisioner Class."""
from boardfarm.devices import debian


class Provisioner(debian.DebianBox):
    """Base Class for debian Provisioner device."""

    model = "base_provisioner"
    name = "provisioner"
    sign_check = True
    standalone_provisioner = True
    default_lease_time = 604800
    max_lease_time = 604800
    is_env_setup_done = False
    tftp_device = None
    tftp_dir = "/tftpboot"
    shared_tftp_server = False

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        # Initialization parameters will differ based on environment
        # Note this setting in case you want provisioner to act as TFTP server
        if "options" in kwargs:
            options = [x.strip() for x in kwargs["options"].split(",")]
            for opt in options:
                # Not a well supported config, will go away at some point
                if opt.startswith("wan-cmts-provisioner"):
                    self.wan_cmts_provisioner = True
                    self.shared_tftp_server = True
                    # This does run one.. but it's handled via the provisioning code path
                    self.standalone_provisioner = False

    def setup_dhcp6_config(self, board_config):
        """Set up DHCP 6 Config."""
        raise NotImplementedError

    def setup_dhcp_config(self, board_config):
        """Set up DHCP Config."""
        raise NotImplementedError

    def get_timzone_offset(self, timezone):
        """Get time zone offset."""
        raise NotImplementedError

    def update_cmts_isc_dhcp_config(self, board_config):
        """Update cmts isc DHCP config."""
        self.setup_dhcp_config(board_config)
        self.setup_dhcp6_config(board_config)
        raise NotImplementedError

    @staticmethod
    def setup_dhcp_env(device):
        """Yet to define the function. Throws exception for now."""
        raise NotImplementedError

    def print_dhcp_config(self):
        """Print DHCP config."""
        raise NotImplementedError

    def provision_board(self, board_config):
        """Reprovisions current board with new board cfg.

        Fetch the config details from args and provision the board.
        Provisioning includes encoding and upload of configuration to TFTP

        :param board_config: board configurations
        :type board_config: dict
        """
        raise NotImplementedError

    def get_ipv4_time_server(self):
        """Return ipv4 time server."""
        raise NotImplementedError

    def get_aftr_name(self):
        """Return after name."""
        raise NotImplementedError

    def start_tftp_server(self):
        """Yet to be implemented. Throws exception for now."""
        self.install_pkgs()
        if self.shared_tftp_server:
            # perform the rest
            raise NotImplementedError
        raise NotImplementedError

    # mode can be "ipv4" or "ipv6"
    def restart_tftp_server(self, mode=None):
        """To apply configuration changes made to TFTP server."""
        raise NotImplementedError

    def copy_file_to_server(self, file_path):
        """Copy a config file to remote/local server.

        2 approaches:
            - SCP the File using
              ``boardfarm.lib.common.scp_from(fname, server, username, password, port, dest)``
            - use gunzip approach to write file in remote. use parent method of linux.
              ``super().copy_file_to_server(file_path)``
        """
        raise NotImplementedError
