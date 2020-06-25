import atexit

from boardfarm.devices import linux


class BaseBoard(linux.LinuxDevice):
    """Base Class implementation for board

    Include all base functionalities defined in linux platform class.
    """
    model = "base_board"
    name = "board"
    wan_iface = None
    lan_iface = None
    conn_list = None
    consoles = []
    prompt = []
    uprompt = []
    uboot_eth = "eth0"
    linux_booted = False
    saveenv_safe = True
    tftp_server_int = None
    flash_meta_booted = False
    has_cmts = False
    cdrouter_config = None
    uboot_net_delay = 30
    routing = True
    tmpdir = "/tmp"

    def __init__(self, *args, **kwargs):
        """Base implementation for board device.

        This method fetches parameters from boardfarm.config and
        initializes the device class.

        If a board has separate console for packet processing,
        device class initialization will be in form of composition.

        A sample example can be:
        ``self.pp_core = connect_pp()``
        ``self.system_core = connect_main()``

        A prompt needs to be defined per core.
        This will not be considered in base board
        """

        self.encoding = 'latin1'
        self.conn_type = kwargs.get('connection_type', None)
        self.connection_cmd = kwargs.get('conn_cmd', [])
        self.config = kwargs.get('config', None)
        self.outlet = kwargs.get('power_outlet', None)
        self.power_ip = kwargs.get('power_ip', None)
        self.username = kwargs.get('power_username', None)
        self.password = kwargs.get('power_password', None)
        self.consoles = []
        for _ in self.connection_cmd:
            # create ur connect statement to the core
            # append the object to self.consoles
            raise Exception("Not implemented!")

        atexit.register(self.kill_console_at_exit)

    def get_logfile_read(self):
        '''Returns logfile_read for main core (ARM)'''
        raise Exception("Not implemented!")

    def set_logfile_read(self, value):
        '''Sets logfile_read for each core af board'''
        raise Exception("Not implemented!")

    logfile_read = property(get_logfile_read, set_logfile_read)

    def set_prompt(self, console, ps):
        """Sets the prompt of a given console.
        This method is idempotent.
        """
        raise Exception("Not implemented!")

    def enter_mainMenu(self):
        """Enter into main menu of system core for board.

        View will differ based on board type.
        """
        raise Exception("Not implemented!")

    def _check_link(self, board, reset):
        """Verify error messages during BIOS setup phase.

        :return: True if no error messages are found
        :rtype: bool
        """
        raise Exception("Not implemented!")

    def wait_for_boot(self):
        """Enter boot loader menu, by interrupting boot-up of board's core.

        In case of more than one core on the board,
        method uses multithreading to trigger interrupt for each core in parallel.

        This method is called to flash new kernel images.
        """
        raise Exception("Not implemented!")

    def get_dns_server(self):
        """Get the DNS server configure on board by provisioner
        This detail is provided to LAN clients connected to board.

        :return: Ip of the nameserver
        :rtype: string
        """
        raise Exception("Not implemented!")

    def _flash_linux(self, KERNEL):
        """This method will download the new kernel images using tftp and
        flash them on system core.

        In order to flash kernel with new image, we need to enter bootloader menu
        i.e. board.wait_for_boot()

        :Param KERNEL: Pass the kernel image which is passed via argument -k <image>
        :type KERNEL: string
        """
        raise Exception("Not implemented!")

    def flash_linux(self, KERNEL):
        "Ensure safe exit in case of flash failure"
        try:
            self._flash_linux(KERNEL)
        except Exception:
            print("NOTICE: REBOOTING!!!!!!!!")
            raise

    def _flash_rootfs(self, ROOTFS):
        """This method will download the new kernel images using tftp and
        flash them on system core.

        In order to flash kernel with new image, we need to enter bootloader menu
        i.e. board.wait_for_boot()

        :Param ROOTFS: Pass the rootfs image which is passed via argument -r <image>
        :type ROOTFS: string
        """
        raise Exception("Not implemented!")

    def flash_rootfs(self, ROOTFS):
        "Ensure safe exit in case of flash failure"
        try:
            self._flash_rootfs(ROOTFS)
        except Exception:
            print("NOTICE: REBOOTING!!!!!!!!")
            raise

    def _flash_all(self, ALL):
        """This method will download the new COBINED SDK images using
        tftp and flash it for multiple core boards in a single call.

        In order to flash  with new image, we need to enter bootloader menu
        i.e. board.wait_for_boot()

        :Param ALL: Pass the combined SDK image
        :type ALL: string
        """
        raise Exception("Not implemented!")

    def flash_all(self, COMBINED):
        "Ensure safe exit in case of flash failure"
        try:
            self._flash_all(COMBINED)
        except Exception:
            print("NOTICE: REBOOTING!!!!!!!!")
            raise

    def is_online(self):
        """Check the status of board

        :return: True if it is operational else False
        :rtype: Boolean
        """
        raise Exception("Not implemented!")

    def wait_for_network(self):
        """Wait for network will wait until board's status is operational after a reboot
        """
        raise Exception("Not implemented!")

    def wait_for_linux(self):
        """Verify if board is able to initialize prompt after bootup.
        """
        raise Exception("Not implemented!")

    def enable_pp(self):
        """Enable packet processing for the board.
        """
        raise Exception("Not implemented!")

    def disable_pp(self):
        """Disable packet processing for the board
        """
        raise Exception("Not implemented!")

    def get_current_cfg_name(self, mta=False):
        """Gets the name of the current board/mta config file from the board device
        2 possible ways:
        - look in /var/tmp on the arm console of the device for .cfg/.bin file

        :param mta: mta flag should be true to get mta cfg name
        :type mta: boolean
        :return: config file name which is booted in the device
        :rtype: string
        """
        raise Exception("Not implemented!")

    def cfg_sha3(self, mta=False):
        """Get sha3sum output of config file booted on the device

        :param mta: mta flag should be true to get mta cfg name, defaults to false
        :type mta: boolean
        :return: secure has algorithm of config
        :rtype: string
        """
        raise Exception("Not implemented!")

    def show_board_config(self):
        """Prints the current decompiled config (if present) on board console
        This function should be used only for debugging purposes.

        :return: checks the config file and return the name of the file
        :rtype: string
        """
        raise Exception("Not implemented!")

    def get_interface_ipaddr(self, iface):
        """Intercept and handle some interface queries depending on the core of board.

        :param iface: to get the ipaddress
        :type ifcae: string
        """
        raise Exception("Not implemented!")

    def get_interface_ip6addr(self, iface):
        """Intercept and handle some interface queries depending on the core of board.

        :param iface: to get ipv6 address
        :type iface: string
        """
        raise Exception("Not implemented!")

    def flash_meta(self,
                   META,
                   wan,
                   lan,
                   alt_tftp_server=None,
                   check_version=False,
                   nosh_image=False):
        """Flashes a combine signed image over TFTP initated by SNMP commands

        :param META: image which is passed via argument -m
        :type META: string
        :param wan: device
        :param lan: device
        :param alt_tftp_server: tftp server ip, defaults to None
        :type alt_tftp_server: string, optional
        :param check_version: True or False , defaults to False
        :param nosh_image: True or False , defaults to False
        """
        raise Exception("Not implemented!")

    def get_interface_macaddr(self, iface):
        """Get the interface mac address of an iface from arm console

        :param iface: interface to get mac
        :type iface: string
        :return: Mac address of the interface
        :rtype: string
        """
        raise Exception("Not implemented!")

    def get_cm_mac_addr(self, iface="wan0"):
        """Get CM MAC Address for an iface for given interface.

        :param iface: Default it will take the wan interface
        :type iface: string,
        :return: Mac address of the interface
        :rtype: string
        """
        raise Exception("Not implemented!")

    def waiting_on_board(self):
        """Waits for the board to become functional/usable after boot-up
        """
        self.wait_for_linux()
        self.wait_for_network()

    def reboot_modem_os(self, s=None):
        """ Reboots the OS via board console
        """
        raise Exception("Not implemented!")

    def upload_config_to_tftp(self, cfg_path, tftp_ip):
        """Pushes board's config file to remote TFTP server.
        TFTP IP must be northbound of board.

        :param cfg_path: abs_path of cfg file on board.
        :type cfg_path: string
        :param tftp_ip: remote ip of TFTP server
        :type tftp_ip: string
        """
        raise Exception("Not implemented!")

    def setup(self, provisioner, **kwargs):
        "Generate config file, perform necessary configuration in provisioner."
        raise Exception("Not implemented!")

    def kill_console_at_exit(self):
        """Kill board console while exiting.
        __init__ will register this method to atexit

        Yields:
        os.kill(pexpect_pid, signal.SIGKILL)
        """
        raise Exception("Not implemented!")

    def restart_tr069(self, ip_mode='ipv4', recheck_times=5):
        """Initialize TR069 component in a board

        :param ip_mode: can be ipv4 or ipv6 or both, defaults to 'ipv4'
        :type ip_mode: string, optional
        :param recheck_times: iteration to re check , defaults to 5
        :type recheck_times: integer, optional
        :raises exception: Failed to connect ACS server
        :return: return a message Connection to ACS succeeded
        :rtype: string
        """
        raise Exception("Not implemented!")

    def reset(self, break_into_uboot=False):
        """Perform a soft/hard reset on board
        """
        raise Exception("Not implemented!")

    def enable_logs(self, flag="enable", component=None):
        """Enable or disable console logs from board main menu

        :param flag: "enable" or "disable" , defaults to enable
        :type flag: string , optional
        :param component: if any specific components, defaults to None
        :type component: string, optional
        :raises assert: failed to enable/disable logger component
        """
        raise Exception("Not implemented!")

    def check_sip_endpoints_registration(self, lines={0: 'TRUE', 1: 'TRUE'}):
        """To validate the Registration status of the sip endpoint(s) connected
        to the MTA lines 0 and/or 1.
        :param lines: dictionary containing the line numbers as keys(0/1) and
                      expected Registered status as values('TRUE'/'FALSE') ,
                      defaults to line 0 and 1 with 'TRUE'
                      ex:
                      board.check_sip_endpoints_registration(lines={0: "FALSE", 1: "TRUE"})
                      board.check_sip_endpoints_registration(lines={0: "FALSE", 1: "FALSE"})
                      board.check_sip_endpoints_registration(lines={1: "FALSE"})
                      board.check_sip_endpoints_registration(lines={0: "TRUE"})
        :type lines: dict, optional
        :raises Exception: failed to verify the expected Status
        """
        raise Exception("Not implemented!")

    def send_sip_offhook_onhook(self, flag="offhook", tcid="0"):
        """send offhook/onhook event on sip server

        :param flag: "offhook" or "onhook", defaults to "offhook"
        :type flag: string, optional
        :param tcid: tcid of the number, defaults to "0"
        :type tcid: string, optional
        """
        raise Exception("Not implemented!")

    def check_media_started(self, tcid="0"):
        """To expect media started string after the device answers the call
        This string is expected as soon as the answer method is called.

        :param tcid: tcid of the number, defaults to "0"
        :type tcid: string, optional
        :return: output of the answer function
        :rtype: string
        """
        raise Exception("Not implemented!")

    def enter_voice_menu(self):
        """To enter voice menu of board.
        """
        raise Exception("Not implemented!")

    def capture_stopping_signal(self, signal_num='30', dial_flag=False):
        """This function could be called along with offhook or with dial function

        :param signal_num: signal_num of the stopping signal, defaults to '30'
        :type signale_num: string, optional
        :param dial_flag: True or False, defaults to False
        :type dial_flag: boolean
        """
        raise Exception("Not implemented!")

    def get_ifaces_ip_dict(self, ifaces=None):
        """To return the dict of ipaddress of interfaces.
        This method is to get the dictionary of all the avalibale ip adress for
        wan, erouter and mta device which intern can be used for pre  validations.

        return: dictionary containing the ip details.
        rtype: dictionay
        """
        raise Exception("Not implemented!")

    def print_info(self, c):
        """Runs a a series of diagnostic commands on the given core.

        This can be used to display the status of a core when a test fails.

        :param c: the console to run the commands on (Atom or Arm)
        :type c: console object
        """
        raise Exception("Not implemented!")

    def check_status(self):
        """Checks status on all cores of a board
        """
        raise Exception("Not implemented!")

    def check_iface_exists(self, iface):
        """Verify if an interface exist on requested core of board.

        :param iface: requested iface
        :type iface: str
        :return: True or False
        :rtype: bool
        """
        raise Exception("Not implemented!")

    def close(self, *args, **kwargs):
        """Close console connections of a board
        """
        raise Exception("Not implemented!")

    def enable_time_display(self, flag="1"):
        """Enable or disable from board's main menu.

        :param flag: "1"(enable) or "0"(disable); defaults to 1(enable)
        :type flag: string
        """
        raise Exception("Not implemented!")

    def get_seconds_uptime(self):
        """Provide uptime value of a board

        :return: string version of datetime
        :rtype: str
        """
        raise Exception("Not implemented!")

    def reset_defaults_via_console(self):
        """ Factory Reset Board
        """
        raise Exception("Not implemented!")

    def unlock_bootloader(self):
        """Simple function to unlock the bootloader of a board
        Assumes:
            - the mirror server is racheable by the board
            - the board is online
        """
        raise Exception("Not implemented!")

    def get_file(self, fname, lan_ip=""):
        """Download the file via a webproxy from webserver.

        E.g. A device on the board's LAN
        """
        raise Exception("Not implemented!")

    def tftp_get_file(self, host, filename, timeout=30):
        """Download file from tftp server."""
        raise Exception("Not implemented!")

    def prepare_file(self,
                     fname,
                     tserver=None,
                     tusername=None,
                     tpassword=None,
                     tport=None):
        """Copy file to tftp server, so that it it available to tftp or
        to the board itself."""
        raise Exception("Not implemented!")

    def network_restart(self):
        """Restart networking.

        Equivalent to ``/etc/init.d/networking restart``
        """
        raise Exception("Not implemented!")

    def firewall_restart(self):
        """Restart the firewall. Return how long it took.

        Equivalent to ``/etc/init.d/firewall restart``

        :return: time taken to restart firewall
        :rtype: str(datetime.datetime)
        """
        raise Exception("Not implemented!")

    def get_wan_iface(self):
        """Return name of WAN interface."""
        raise Exception("Not implemented!")

    def config_wan_proto(self, proto):
        """Set protocol for WAN interface."""
        raise Exception("Not implemented!")

    def enable_mgmt_gui(self):
        """Allow access to webgui from devices on WAN interface."""
        raise Exception("Not implemented!")

    def enable_ssh(self):
        """Allow ssh on wan interface."""
        raise Exception("Not implemented!")

    def get_pp_dev(self):
        """Return packet processing core of the board

        :return: instance of PP core
        :rtype: object
        """
        raise Exception("Not implemented!")

    def collect_stats(self, stats=[]):
        """Collect board stats for multiple functionalities to monitor
        """
        raise Exception("Not implemented!")

    def parse_stats(self, dict_to_log={}):
        """Parse collected stats of board for logging.
        """
        raise Exception("Not implemented!")
