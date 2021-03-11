from abc import abstractmethod

import boardfarm.devices.connection_decider as conn_dec
from boardfarm.devices import get_device_mapping_class
from boardfarm.exceptions import CodeError
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper as PexpectHelper
from boardfarm.lib.signature_checker import __MetaSignatureChecker


class ConsoleTemplate(PexpectHelper, metaclass=__MetaSignatureChecker):
    """ABC connection class"""

    name = ""
    conn_type = None
    conn_cmd = None
    prompt = None

    @abstractmethod
    def __init__(self, conn_type: str, conn_cmd: str, **kwargs):
        """Initializer for the ABC connection class"""
        self.conn_type = conn_type
        self.conn_cmd = conn_cmd
        self.prompt = kwargs.get("prompt", None)
        self.spawn_device()

    @abstractmethod
    def connect(self):
        """Connects to the device"""

    @abstractmethod
    def close(self):
        """Closes the connection to the device"""

    def spawn_device(self, **kwargs):
        """Spwans a console device based on the class type specified in
        the paramter device_type. Currently the communication with the console
        occurs via the pexpect module."""
        self.connection = conn_dec.connection(
            self.conn_type, device=self, conn_cmd=self.conn_cmd
        )


class BoardHWTemplate(metaclass=__MetaSignatureChecker):
    @abstractmethod
    def __init__(self, *args, **kwargs):
        """Base initialisation of the DUT HW interface."""
        conn_cmd = kwargs.get("conn_cmd")
        conn_type = kwargs.get("conn_type")
        self.consoles = [ConsoleTemplate(conn_type, c) for c in conn_cmd]
        self.connect(*args, **kwargs)

    @abstractmethod
    def connect(self, *args, **kwargs):
        """This may not be needed. Connects to the DUT. """
        for c in self.consoles:
            c.connect()

    def is_production(self):
        """Returns True if no debug features are available on the DUT. E.g.
        produciton DUTs do not have debug consoles, and the only logging
        available is via a remote logger (if/when configured)."""
        return not bool(self.consoles)

    @abstractmethod
    def reset(self):
        """Resets/reboot the board via HW (usually via a PDU device)"""

    @abstractmethod
    def flash(self, image: str, method: str = None):
        """Can be overridden to implement flashing via bootloader."""

    @abstractmethod
    def close(self):
        for c in self.consoles:
            c.close()


class BoardSWTemplate(metaclass=__MetaSignatureChecker):
    @abstractmethod
    def __init__(self, hw: BoardHWTemplate, **kwargs):
        """Base initialisation of the board SW."""

    @abstractmethod
    def is_production(self):
        """If True the SW running is production like, e.g. missing debug
        consoles, logging limited to boot splash messages, debug messages are
        sent to a remote logger (if/when configured).
        Vendors usually allow produciton like images can be run on debug HW."""

    def reset(self, method: str = None):
        """Resets/reboot the board via SW (usually via a debug console comand)
        this may not be possible as it is dependend on the SW loaded on the DUT."""
        raise NotImplementedError


class BoardTemplate(metaclass=__MetaSignatureChecker):
    """This class shows a basic set of interfaces to be implemented for testing
    a DUT with boardfarm. The DUT attributes (and other devices) are defined
    a .json file (called "inventory file")."""

    def __init__(self, *args, **kwargs):
        """Base initialisation of the board device. Used to store the necessary
        values that are then used to drive the HW via the AbstractBoardHW
        derived class."""

    @property
    @abstractmethod
    def cm_mac(cls):
        """The DUT mac address"""

    @property
    @abstractmethod
    def model(cls):
        """This attribute is used by boardfarm to select the class to be used
        to create the object that allows the test fixutes to access the DUT.
        This property shall return a value that matches the "board_type"
        attribute in the inventory file."""

    @property
    @staticmethod
    @abstractmethod
    def hw(self):
        """DUT hardware related object. This attribute will have the consoles
        connections (if any) and the methods used to access the HW"""

    @property
    @staticmethod
    @abstractmethod
    def sw(self):
        """DUT software related object. This attribute will have all teh methods
        that are SW version dependent."""

    @abstractmethod
    def flash(self, image: str, method: str = None):
        """Flashes the given image according to the 'method'.
        Method can be defined by the implemetation as needed.
        Examples: flash via bootloader, snmp, etc.
        Once the FW is flashed the SW class can be reloaded."""
        sw = self.env_helper.get_software()
        self.reload_sw_object(sw["image_uri"].split("/")[-1])

    @abstractmethod
    def reset(self, method: str = None):
        """Resets/reboot the board according to the 'method'.
        Method can be defined by the implemetation as needed.
        Examples: reset via PDU (HW reset), via OS console (SW reset), via snmp,
        via other device (ACS), etc"""

    @abstractmethod
    def factory_reset(self, method: str = None):
        """Resets the board to default settings according to the 'method'.
        Method can be defined by the implemetation as needed.
        Examples: reset via PDU, via OS console, via snmp, via other device
        (ACS), etc"""

    def reload_sw_object(self, sw):
        sw_class = get_device_mapping_class(sw)
        if sw_class:
            self.sw = sw_class(self.hw)
        else:
            raise CodeError(f"class for {sw} not found")
        self.sw.version = self.sw.get_sw_version()

    def _sendline(self, *args, **kwargs):
        """Communicate with the console. Not to be used in a testcase
        This method maybe deprecated/removed in a near future"""
        return self.hw.consoles[0].sendline(*args, **kwargs)

    def _expect(self, *args, **kwargs):
        """Communicate with the console. Not to be used in a testcase
        This method maybe deprecated/removed in a near future"""
        return self.hw.consoles[0].expect(*args, **kwargs)

    def interact(self):
        """Provides interaction with the current session. Useful for manual
        debugging."""
        self.hw.consoles[0].interact()

    @abstractmethod
    def close(self):
        """TBD, needed by bft"""
        self.hw.close()
