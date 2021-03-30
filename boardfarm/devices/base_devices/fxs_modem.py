from abc import abstractmethod

from boardfarm.devices.linux import LinuxInterface


class FXSModemTemplate(LinuxInterface):
    @property
    @abstractmethod
    def model(cls):
        """This attribute is used by boardfarm to match parameters entry from config
        and initialise correct object.

        This property shall be any string value that matches the "type"
        attribute of FSX entry in the inventory config file.
        See devices/serialphone.py as a reference
        """

    @abstractmethod
    def phone_start(self, baud: str = "115200", timeout: str = "1") -> None:
        """Connect to the serial line of FXS modem

        :param baud: serial baud rate, defaults to "115200"
        :type baud: str, optional
        :param timeout: connection timeout, defaults to "1"
        :type timeout: str, optional
        """

    @abstractmethod
    def phone_kill(self) -> None:
        """Close the serial connection."""

    @abstractmethod
    def on_hook(self) -> None:
        """Execute the HAYES ATA command for on_hook procedure.

        On hook. Hangs up the phone, ending any call in progress.
        Need to send ATH0 command over FXS modem
        """

    @abstractmethod
    def off_hook(self) -> None:
        """Execute the HAYES ATA command for on_hook procedure.

        Off hook. Picks up the phone line (typically you'll hear a dialtone)
        Need to send ATH1 command over FXS modem
        """

    @abstractmethod
    def dial(self, number: str, receiver_ip: str = None) -> None:
        """Execute Hayes ATDT command for dialing a number in FXS modems.

        FXS modems simulate analog phones and requie ISDN/PSTN number to dial.
        In case of dialing a SIP enabled phone, please specify receiver IP
        to dial using an auto-generated SIP URL.

        :param number: Phone number to dial
        :type number: str
        :param receiver_ip: SIP URL IP address, defaults to None
        :type receiver_ip: str, optional
        """
