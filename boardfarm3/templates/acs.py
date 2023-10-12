"""Boardfarm ACS device template."""

from abc import ABC, abstractmethod
from typing import Literal, Optional, Union

# pylint: disable=invalid-name


GpvStruct = dict[str, Union[str, int, bool]]
SpvStruct = dict[str, Union[str, int, bool]]
SpvInput = Union[SpvStruct, list[SpvStruct]]
GpvInput = Union[str, list[str]]
GpvResponse = list[GpvStruct]


class ACS(ABC):
    """Boardfarm ACS device template."""

    @abstractmethod
    def GPA(self, param: str, cpe_id: Optional[str] = None) -> list[dict]:
        """Execute GetParameterAttributes RPC call for the specified parameter.

        Example usage:

        >>> acs_server.GPA('Device.WiFi.SSID.1.SSID')

        :param param: parameter to be used in get
        :type param: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
        :return: dictionary with keys Name, AccessList, Notification indicating the GPA
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def SPA(  # noqa: PLR0913
        self,
        param: Union[list[dict], dict],
        notification_param: bool = True,
        access_param: bool = False,
        access_list: Optional[list] = None,
        cpe_id: Optional[str] = None,
    ) -> list[dict]:
        """Execute SetParameterAttributes RPC call for the specified parameter.

        Example usage:

        >>> acs_server.SPA({'Device.WiFi.SSID.1.SSID':'1'}),

        could be parameter list of dicts/dict containing param name and notifications

        :param param: parameter as key of dictionary and notification as its value
        :type param: Union[list[dict], dict]
        :param notification_param: If True, the value of Notification replaces the
            current notification setting for this Parameter or group of Parameters.
            If False, no change is made to the notification setting
        :type notification_param: bool
        :param access_param: If True, the value of AccessList replaces the current
            access list for this Parameter or group of Parameters.
            If False, no change is made to the access list
        :type access_param: bool
        :param access_list: Array of zero or more entities for which write access to
            the specified Parameter(s) is granted
        :type access_list: list, optional
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
        :return: SPA response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def GPV(
        self,
        param: GpvInput,
        timeout: Optional[int] = None,
        cpe_id: Optional[str] = None,
    ) -> GpvResponse:
        """Execute GetParameterValues RPC call for the specified parameter(s).

        :param param: name of the parameter(s) to perform RPC
        :type param: GpvInput
        :param timeout: to set the Lifetime Expiry time, defaults to None
        :type timeout: Optional[int]
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
        :return: GPV response with keys, value and datatype
            Example:

            .. code-block:: python

                [ {
                    'key':'Device.WiFi.AccessPoint.1.AC.1.Alias',
                    'value':'mok_1',
                    'type':'string'
                } ]

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
        """Execute SetParameterValues RPC call for the specified parameter.

        :param param_value: dictionary that contains the path to the key and
            the value to be set. Example:
            .. code-block:: python

                { 'Device.WiFi.AccessPoint.1.AC.1.Alias': 'mok_1' }

        :type param_value: SpvInput
        :param timeout: wait time for the RPC to complete, defaults to None
        :type timeout: Optional[int]
        :param cpe_id: CPE identifier, defaults to None
        :type cpe_id: Optional[str]
        :return: status of the SPV, either 0 or 1
        :rtype: int
        """
        raise NotImplementedError

    @abstractmethod
    def FactoryReset(self, cpe_id: Optional[str] = None) -> list[dict]:
        """Execute FactoryReset RPC.

        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the reboot of the device has to be handled in the test.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
        :return: factory reset response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def Reboot(self, CommandKey: str, cpe_id: Optional[str] = None) -> list[dict]:
        """Execute Reboot RPC.

        :param CommandKey: reboot command key
        :type CommandKey: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
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
    ) -> list[dict]:
        """Execute AddOjbect RPC call for the specified parameter.

        :param param: parameter to be used to add
        :type param: str
        :param param_key: the value to set the ParameterKey parameter, defaults to ""
        :type param_key: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
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
    ) -> list[dict]:
        """Execute DeleteObject RPC call for the specified parameter.

        :param param: parameter to be used to delete
        :type param: str
        :param param_key: the value to set the ParameterKey parameter, defaults to ""
        :type param_key: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
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
    ) -> list[dict]:
        """Execute GetParameterNames RPC call for the specified parameter.

        :param param: parameter to be discovered
        :type param: str
        :param next_level: displays the next level children of the object if marked true
        :type next_level: bool
        :param timeout: Lifetime Expiry time
        :type timeout: Optional[int]
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
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
    ) -> list[dict]:
        """Execute ScheduleInform RPC.

        :param CommandKey: string to return in the CommandKey element of the
            InformStruct when the CPE calls the Inform method, defaults to "Test"
        :type CommandKey: str
        :param DelaySeconds: number of seconds from the time this method is
            called to the time the CPE is requested to initiate a one-time Inform
            method call, defaults to 20
        :type DelaySeconds: int
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str], optional
        :return: returns ScheduleInform response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def GetRPCMethods(self, cpe_id: Optional[str] = None) -> list[dict]:
        """Execute GetRPCMethods RPC.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: Optional[str]
        :return: GetRPCMethods response of supported functions
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def Download(  # pylint: disable=too-many-arguments  # noqa: PLR0913
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
    ) -> list[dict]:
        """Execute Download RPC.

        :param url: URL to download file
        :type url: str
        :param filetype: the string paramenter from following 6 values only

            .. code-block:: python

                [
                    "1 Firmware Upgrade Image", "2 Web Content",
                    "3 Vendor Configuration File", "4 Tone File",
                    "5 Ringer File", "6 Stored Firmware Image"
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
        :type cpe_id: Optional[str]
        :return: returns Download response
        :rtype: list[dict]
        """
        raise NotImplementedError

    @abstractmethod
    def provision_cpe_via_tr069(
        self,
        tr069provision_api_list: list[dict[str, list[dict[str, str]]]],
        cpe_id: str,
    ) -> None:
        """Provision the cpe with tr069 parameters defined in env json.

        :param tr069provision_api_list: List of tr069 operations and their values
        :type tr069provision_api_list: list[dict[str, list[dict[str, str]]]]
        :param cpe_id: cpe identifier
        :type cpe_id: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        raise NotImplementedError

    @abstractmethod
    def perform_scp(
        self,
        source: str,
        destination: str,
        action: Literal["download", "upload"] = "download",
    ) -> None:
        """Perform SCP from linux device.

        :param source: source file path
        :type source: str
        :param destination: destination file path
        :type destination: str
        :param action: scp action(download/upload), defaults to "download"
        :type action: Literal["download", "upload"], optional
        """
        raise NotImplementedError
