from abc import abstractmethod
from typing import Any, Dict, List, Optional, Union

from boardfarm.lib.signature_checker import __MetaSignatureChecker

GpvStruct = Dict[str, Union[str, int, bool]]
SpvStruct = Dict[str, Union[str, int, bool]]
SpvInput = Union[SpvStruct, List[SpvStruct]]
GpvInput = Union[str, List[str]]
GpvResponse = List[GpvStruct]


class AcsTemplate(metaclass=__MetaSignatureChecker):
    """ACS server connector template class.
    Contains basic list of APIs to be able to use TR069 intercation with CPE
    All methods, marked with @abstractmethod annotation have to be implemented in derived
    class with the same signatures as in template.
    """

    @property
    @abstractmethod
    def model(self):
        """This attribute is used by boardfarm to match parameters entry from config
        and initialise correct object.
        This property shall be any string value that matches the "type"
        attribute of ACS entry in the inventory config file.
        See devices/axiros_acs.py as a reference
        """

    @property
    @abstractmethod
    def url(self):
        """This is the URL to access the ACS."""

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        """Initialize ACS parameters.
        Config data dictionary will be unpacked and passed to init as kwargs.
        You can use kwargs in a following way:
            self.username = kwargs.get("username", "DEFAULT_USERNAME")
            self.password = kwargs.get("password", "DEFAULT_PASSWORD")
        Be sure to add
            self.connect()
        at the end in order to properly initialize device on init step
        """

    @abstractmethod
    def connect(self, *args, **kwargs) -> None:
        """Connect to ACS & initialize session. Can be done using any http(s) library.
        Here you can run initial commands in order to land on specific prompt
        and/or initialize system
        E.g. enter username/password, set stuff in device config or disable pagination"""
        raise NotImplementedError

    @abstractmethod
    def GPV(
        self,
        param: GpvInput,
        timeout: Optional[int] = None,
        cpe_id: Optional[str] = None,
    ) -> GpvResponse:
        """Send GetParamaterValues command via ACS server.

        :param param: TR069 parameters to get values of
        :type param: GpvInput
        :param timeout: wait time for the RPC to complete
        :type timeout: int, optional
        :param cpe_id: CPE identifier, defaults to None
        :type cpe_id: str, optional
        :return: List of all the attributes with Key, Value and Datatype
            E.g.[
                    {
                    'key':'Device.WiFi.AccessPoint.1.AC.1.Alias',
                    'value':'mok_1',
                    'type':'string'
                    }
                ]
        :rtype: GpvResponse
        """
        raise NotImplementedError

    @abstractmethod
    def SPV(
        self,
        param_value: SpvInput,
        timeout: Optional[int] = None,
        cpe_id: Optional[str] = None,
    ) -> int:
        """Send SetParamaterValues command via ACS server.

        :param param_value: dictionary that contains the path to the key and
            the value to be set.
            E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :type param_value: SpvInput
        :param timeout: wait time for the RPC to complete
        :type timeout: int, optional
        :param cpe_id: CPE identifier, defaults to None
        :type cpe_id: str, optional
        :return: status of the SPV i.e. either 0 or 1
        :rtype: int
        """
        raise NotImplementedError

    @abstractmethod
    def FactoryReset(self, cpe_id: Optional[str] = None) -> List[dict]:
        """Execute FactoryReset RPC.

        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the reboot of the device has to be handled in the test.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: factory reset response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def interact(self) -> None:
        """Initiate the Interact session."""
        raise NotImplementedError

    @abstractmethod
    def GPA(
        self,
        param: Union[str, List[str]],
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Get parameter attribute of the parameter specified.

        Example usage:

        >>> acs_server.GPA("Device.WiFi.SSID.1.SSID")

        :param param: parameter to be used in get
        :type param: str | list[str]
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: dictionary with keys Name, AccessList, Notification indicating the GPA
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def SPA(
        self,
        param: Union[List[dict], dict],
        notification_param: bool = True,
        access_param: bool = False,
        access_list: Optional[List] = None,
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Set parameter attribute of the parameter specified.

        Example usage:

        >>> (acs_server.SPA({"Device.WiFi.SSID.1.SSID": "1"}),)

        could be parameter list of dicts/dict containing param name and notifications

        :param param: parameter as key of dictionary and notification as its value
        :type param: list[dict]|dict
        :param notification_param: If True, the value of Notification replaces the
            current notification setting for this Parameter or group of Parameters.
            If False, no change is made to the notification setting
            Defaults to True
        :type notification_param: bool
        :param access_param: If True, the value of AccessList replaces the current
            access list for this Parameter or group of Parameters.
            If False, no change is made to the access list
            Defaults to False
        :type access_param: bool
        :param access_list: Array of zero or more entities for which write access to
            the specified Parameter(s) is granted
            Defaults to None
        :type access_list: list|None
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: SPA response (usually an empty list)
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def Reboot(
        self,
        CommandKey: str = "reboot",
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Execute Reboot.

        :param CommandKey: reboot command key
        :type CommandKey: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: reboot RPC response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def AddObject(
        self,
        param: str,
        param_key: str = "",
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Add object ACS of the parameter specified i.e a remote procedure call.

        :param param: parameter to be used to add
        :type param: str
        :param param_key: the value to set the ParameterKey parameter, defaults to ""
        :type param_key: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: list of dictionary with key, value, type indicating the AddObject
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def DelObject(
        self,
        param: str,
        param_key: str = "",
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Delete object ACS of the parameter specified i.e a remote procedure call.

        :param param: parameter to be used to delete
        :type param: str
        :param param_key: the value to set the ParameterKey parameter, defaults to ""
        :type param_key: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: list of dictionary with key, value, type indicating the DelObject
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def GPN(
        self,
        param: str,
        next_level: bool,
        timeout: Optional[int] = None,
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Discover the Parameters accessible on a particular CPE.

        :param param: parameter to be discovered
        :type param: str
        :param next_level: displays the next level children of the object if marked true
        :type next_level: bool
        :param timeout: Lifetime Expiry time
        :type timeout: int|None
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: value as a list of dictionary
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def ScheduleInform(
        self,
        CommandKey: str = "Test",
        DelaySeconds: int = 20,
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Execute ScheduleInform RPC.

        :param CommandKey: the string paramenter passed to scheduleInform
        :type CommandKey: str
        :param DelaySeconds: delay of seconds in integer
        :type DelaySeconds: int
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: returns ScheduleInform response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def GetRPCMethods(self, cpe_id: Optional[str] = None) -> List[dict]:
        """Execute GetRPCMethods RPC.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: GetRPCMethods response of supported functions
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def Download(  # noqa: PLR0913
        self,
        url: str,
        filetype: str = "1 Firmware Upgrade Image",
        targetfilename: str = "",
        filesize: int = 200,
        username: str = "",
        password: str = "",
        commandkey: str = "",
        delayseconds: int = 10,
        successurl: str = "",
        failureurl: str = "",
        cpe_id: Optional[str] = None,
    ) -> List[dict]:
        """Execute Download RPC.

        :param url: URL to download file
        :type url: str
        :param filetype: the string paramenter from following 6 values only

            .. code-block:: python

                [
                    "1 Firmware Upgrade Image",
                    "2 Web Content",
                    "3 Vendor Configuration File",
                    "4 Tone File",
                    "5 Ringer File",
                    "6 Stored Firmware Image",
                ]

        :type filetype: str
        :param targetfilename: TargetFileName to download through RPC
        :type targetfilename: str
        :param filesize: the size of file to download in bytes
        :type filesize: int
        :param username: User to authenticate with file Server.  Default=""
        :type username: str
        :param password: Password to authenticate with file Server. Default=""
        :type password: str
        :param commandkey: the string paramenter passed in Download API
        :type commandkey: str
        :param delayseconds: delay of seconds in integer
        :type delayseconds: int
        :param successurl: URL to access in case of Download API execution succeeded
        :type successurl: str
        :param failureurl: URL to access in case of Download API execution Failed
        :type failureurl: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :returns: the Download response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def provision_cpe_via_tr069(
        self,
        tr069provision_api_list: List[Dict[str, List[Dict[str, str]]]],
        cpe_id: str,
    ) -> None:
        """Provision the cable modem with tr069 parameters defined in env json.

        :param tr069provision_api_list: List of tr069 operations and their values
        :type tr069provision_api_list: list[dict[str, list[dict[str, str]]]]
        :param cpe_id: cpe identifier
        :type cpe_id: str
        """
        raise NotImplementedError

    @abstractmethod
    def start_tcpdump(
        self,
        interface: str,
        port: Optional[str],
        output_file: str = "pkt_capture.pcap",
        filters: Optional[Dict] = None,
        additional_filters: Optional[str] = "",
    ) -> str:
        """Start tcpdump capture on given interface.

        :param interface: inteface name where packets to be captured
        :type interface: str
        :param port: port number, can be a range of ports(eg: 443 or 433-443)
        :type port: str
        :param output_file: pcap file name, Defaults: pkt_capture.pcap
        :type output_file: str
        :param filters: filters as key value pair(eg: {"-v": "", "-c": "4"})
        :type filters: Optional[Dict]
        :param additional_filters: additional filters
        :type additional_filters: Optional[str]
        :return: console output and tcpdump process id
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def stop_tcpdump(self, process_id: str) -> None:
        """Stop tcpdump capture.

        :param process_id: tcpdump process id
        :type process_id: str
        """
        raise NotImplementedError

    @abstractmethod
    def read_tcpdump(
        self,
        capture_file: str,
        protocol: str = "",
        opts: str = "",
        timeout: int = 30,
        rm_pcap: bool = True,
    ) -> str:
        """Read the given tcpdump and delete the file afterwards.

        :param capture_file: pcap file path
        :type capture_file: str
        :param protocol: protocol to filter
        :type protocol: str
        :param opts: command line options for reading pcap
        :type opts: str
        :param timeout: timeout in seconds for reading pcap
        :type timeout: int
        :param rm_pcap: remove pcap file afterwards
        :type rm_pcap: bool
        :return: tcpdump output
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a file from the device to local storage.

        :param local_path: local file path
        :type local_path: str
        :param source_path: source path on device
        :type source_path: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        raise NotImplementedError
