"""Implementation module for the Axiros restful API device."""

# pylint: disable=E1123

from __future__ import annotations

import ast
import logging
import os
from argparse import Namespace
from copy import deepcopy
from functools import partial
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from debtcollector import moves
from httpx import Client

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import (
    ConfigurationFailure,
    NotSupportedError,
    TR069FaultCode,
    TR069ResponseError,
)
from boardfarm3.lib.networking import IptablesFirewall
from boardfarm3.lib.utils import retry_on_exception
from boardfarm3.templates.acs import ACS, GpvInput, GpvResponse, SpvInput

if TYPE_CHECKING:
    from httpx._types import URLTypes

    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect


_LOGGER = logging.getLogger(__name__)
_DATE_LENGTH = 6
_HTTP_OK = 200  # requests.codes & httpx._status_codes.codes make mypy unhappy


# pylint: disable=duplicate-code,too-many-public-methods
class AxirosACS(LinuxDevice, ACS):
    """Implementation module for the Axirox device via the restful API.

    In its most basic configuration the following are needed:

    .. code-block:: json

        {
            "acs_rest_url": "http://10.71.10.117:9676",
            "name": "acs_server",
            "http_password": "bigfoot1", # see Note below
            "http_username": "admin",    # see Note below
            "type": "axiros_acs_rest",
        }

    This is purely web based and has no console access.

    With console access and provisioning (allows for tcpdump and firewall access):

    .. code-block:: json

        {
            "acs_mib": "http://acs_server.boardfarm.com:9675",
            "color": "blue",
            "connection_type": "authenticated_ssh",
            "http_password": "bigfoot1", # see Note below
            "http_port": 9676,
            "http_username": "admin",    # see Note below
            "ipaddr": "10.71.10.151",
            "max_users": 9999,
            "name": "acs_server",
            "options": "wan-static-ip:172.25.19.40/18,.......",
            "password": "bigfoot1",
            "port": 4501,
            "type": "axiros_acs_rest",
            "acs_rest_url": "http://10.71.10.151:9676", # optional
            "username": "root"
        },

    If "acs_rest_url" is not provided the url is constructed from ipaddr+http_port

    NOTE: The "http_username" and "http_password" can be ommitted and set via the bash
    variables UIM_USR and UIM_PWD.
    """

    @staticmethod
    def _type_conversion(data: Any) -> str:  # noqa: ANN401, # pylint: disable=R0911
        # TODO: Currently a very simple conversion, maybe revisited!
        data_type = type(data)
        if data_type is int:
            return "int"
        if data_type is str:
            return "string"
        if data_type is bool:
            return "boolean"
        if data_type is list and len(data) == _DATE_LENGTH:  # very simple check ATM
            return "date"
        msg = f"Cannot detect type for {data}"
        raise TypeError(msg)

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize ACS parameters.

        :param config: json configuration
        :type config: dict
        :param cmdline_args: command line args
        :type cmdline_args: Namespace
        :raises ConfigurationFailure: on missing
        """
        super().__init__(config, cmdline_args)
        self._firewall: IptablesFirewall | None = None
        self._acs_rest_url = self._config.get(
            "acs_rest_url",
            f"http://{self._config.get('ipaddr')}:{self._config.get('http_port')}",
        )
        self._base_url = urljoin(
            self._acs_rest_url,
            self._config.get(
                "endpoint",
                "/live/CPEManager/DMInterfaces/rest/v1/action/",
            ),
        )
        self._http_username = self._config.get(
            "http_username", os.environ.get("AXIROS_USR", None)
        )
        self._http_password = self._config.get(
            "http_password", os.environ.get("AXIROS_PSW", None)
        )
        if not self._http_username or not self._http_password:
            msg = (
                "The credentials must be given either in the inventory "
                "http_username and http_password or the shell variables "
                "AXIROS_USR and AXIROS_PSW must be defined."
            )
            raise ConfigurationFailure(msg)
        self._client = Client(
            auth=(self._http_username, self._http_password),
            verify=False,  # noqa: S501
        )

    @property
    def url(self) -> str:
        """Returns the acs url used.

        :return: acs url component instance
        :rtype: str
        """
        return f"{self.device_name}.boardfarm.com"

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot AxirosACS device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._check_axiros_connectivity()

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to initialize AxirosACS device."""
        _LOGGER.info(
            "Initializing %s(%s) device with skip-boot option",
            self.device_name,
            self.device_type,
        )
        self._check_axiros_connectivity()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown AxirosACS device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._client.close()

    def _common_setup(
        self, cpe_id: str | None, timeout: int | None
    ) -> dict[str, int | bool]:
        if cpe_id is None:
            msg = f"{cpe_id!r} - Invalid CPE-ID"
            raise ValueError(msg)
        return {"Lifetime": timeout if timeout else 300, "Sync": True}

    def _post(
        self, url: URLTypes, json_payload: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        res = self._client.post(url=url, json=json_payload, timeout=timeout + 30)
        res.raise_for_status()
        json_res: dict[str, Any] = res.json()["Result"]
        if json_res["code"] != _HTTP_OK:
            if "faultcode" in json_res["message"]:
                msg = json_res["message"]
                exc = TR069FaultCode(msg)
                exc.faultdict = ast.literal_eval(msg[msg.index("{") :])
                raise exc
            raise TR069ResponseError(json_res["message"])
        return json_res

    def GPV(
        self,
        param: GpvInput,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> GpvResponse:
        """Send GetParamaterValues command via ACS server.

        :param param: TR069 parameters to get values of
        :type param: GpvInput
        :param timeout: wait time for the RPC to complete
        :type timeout: int|None
        :param cpe_id: CPE identifier, defaults to None
        :type cpe_id: str|None
        :return: list of all the attributes with Key, Value and Datatype
        :rtype: GpvResponse
        """
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)
        if not isinstance(param, list):
            param = [param]
        url = urljoin(self._base_url, "GetParameterValues")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": param,
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = self._type_conversion(value["value"])
            result.append(value)
        return result

    def SPV(
        self,
        param_value: SpvInput,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> int:
        """Send SetParamaterValues command via ACS server.

        :param param_value: dictionary that contains the path to the key and
            the value to be set.
            E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :type param_value: SpvInput
        :param timeout: wait time for the RPC to complete
        :type timeout: int|None
        :param cpe_id: CPE identifier, defaults to None
        :type cpe_id: str|None
        :return: status of the SPV i.e. either 0 or 1
        :rtype: int
        """
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)
        url = urljoin(self._base_url, "SetParameterValues")
        # SpvInput can take a list of dicts, make it a dict with key and vals
        # this is to keep mypy strict happy
        if isinstance(param_value, list):
            param_value = {k: v for x in param_value for k, v in x.items()}
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": [{"key": k, "value": v} for k, v in param_value.items()],
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        return int(json_res["details"][0]["value"])

    def GPA(
        self,
        param: str,
        cpe_id: str | None = None,
    ) -> list[dict]:
        """Get parameter attribute of the parameter specified.

        Example usage:

        >>> acs_server.GPA("Device.WiFi.SSID.1.SSID")

        :param param: parameter to be used in get
        :type param: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: dictionary with keys Name, AccessList, Notification indicating the GPA
        :rtype: list[dict]
        """
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=300)
        url = urljoin(self._base_url, "GetParameterAttributes")
        # TODO: make the template accept a list as param
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": [param],
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        return json_res["details"][0]["value"]

    def SPA(  # pylint: disable=too-many-arguments
        self,
        param: list[dict] | dict,
        notification_param: bool = True,
        access_param: bool = False,
        access_list: list | None = None,
        cpe_id: str | None = None,
    ) -> list[dict]:
        """Set parameter attribute of the parameter specified.

        Example usage :

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
        :return: SPA response (usually and empty list)
        :rtype: list[dict]
        """
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=300)
        url = urljoin(self._base_url, "SetParameterAttributes")
        if not isinstance(param, list):
            param = [param]

        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
        }
        json["Parameters"] = [
            {
                "AccessList": access_list or [],
                "AccessListChange": access_param,
                "Name": next(iter(elem.keys())),
                "Notification": next(iter(elem.values())),
                "NotificationChange": notification_param,
            }
            for elem in param
        ]

        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        return json_res["details"]

    def FactoryReset(self, cpe_id: str | None = None) -> list[dict]:
        """Execute FactoryReset RPC.

        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the reboot of the device has to be handled in the test.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: factory reset response
        :rtype: list[dict]
        """
        timeout = 120
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)

        url = urljoin(self._base_url, "FactoryReset")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = self._type_conversion(value["value"])
            result.append(value)
        return result

    def Reboot(
        self,
        CommandKey: str = "reboot",
        cpe_id: str | None = None,
    ) -> list[dict]:
        """Execute Reboot.

        :param CommandKey: reboot command key
        :type CommandKey: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: reboot RPC response
        :rtype: list[dict]
        """
        timeout = 120
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)

        url = urljoin(self._base_url, "Reboot")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": CommandKey,
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = self._type_conversion(value["value"])
            result.append(value)
        return result

    def AddObject(
        self,
        param: str,
        param_key: str = "",
        cpe_id: str | None = None,
    ) -> list[dict]:
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
        timeout = 120
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)

        url = urljoin(self._base_url, "AddObject")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": {
                "ObjectName": param,
                "ParameterKey": param_key,
            },
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = self._type_conversion(value["value"])
            result.append(value)
        return result

    def DelObject(
        self,
        param: str,
        param_key: str = "",
        cpe_id: str | None = None,
    ) -> list[dict]:
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
        timeout = 120
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)

        url = urljoin(self._base_url, "DeleteObject")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": {
                "ObjectName": param,
                "ParameterKey": param_key,
            },
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = self._type_conversion(value["value"])
            result.append(value)
        return result

    def GPN(
        self,
        param: str,
        next_level: bool,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> list[dict]:
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
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)
        url = urljoin(self._base_url, "GetParameterNames")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": {
                "NextLevel": next_level,
                "ParameterPath": param,
            },
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = self._type_conversion(value["value"])
            value["value"] = str(value["value"]).lower()
            result.append(value)
        return result

    def ScheduleInform(
        self,
        CommandKey: str = "Test",
        DelaySeconds: int = 20,
        cpe_id: str | None = None,
    ) -> list[dict]:
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
        timeout = 120
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)
        url = urljoin(self._base_url, "ScheduleInform")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": {
                "CommandKey": CommandKey,
                "DelaySeconds": DelaySeconds,
            },
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = self._type_conversion(value["value"])
            value["value"] = str(value["value"]).lower()
            result.append(value)
        return result

    def GetRPCMethods(self, cpe_id: str | None = None) -> list[dict]:
        """Execute GetRPCMethods RPC.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str|None
        :return: GetRPCMethods response of supported functions
        :rtype: list[dict]
        """
        timeout = 120
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)
        url = urljoin(self._base_url, "GetRPCMethods")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = ""  # rest does not return any type
            result.append(value)
        return result

    def Download(  # pylint: disable=too-many-arguments,R0914  # noqa: PLR0913
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
        cpe_id: str | None = None,
    ) -> list[dict]:
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
        param = {
            "CommandKey": commandkey,
            "DelaySeconds": delayseconds,
            "FailureURL": failureurl,
            "FileSize": filesize,
            "FileType": filetype,
            "Password": password,
            "SuccessURL": successurl,
            "TargetFileName": targetfilename,
            "URL": url,
            "Username": username,
        }
        timeout = 120
        cmd_opt = self._common_setup(cpe_id=cpe_id, timeout=timeout)
        url = urljoin(self._base_url, "Download")
        json = {
            "CPEIdentifier": {"cpeid": cpe_id},
            "CommandOptions": cmd_opt,
            "Parameters": param,
        }
        json_res = self._post(url=url, json_payload=json, timeout=cmd_opt["Lifetime"])
        result = []
        for val in json_res["details"]:
            value = deepcopy(val)
            value["type"] = ""  # rest does not return any type
            result.append(value)
        return result

    def provision_cpe_via_tr069(
        self,
        tr069provision_api_list: list[dict[str, list[dict[str, str]]]],
        cpe_id: str,
    ) -> None:
        """Provision the cable modem with tr069 parameters defined in env json.

        :param tr069provision_api_list: List of tr069 operations and their values
        :type tr069provision_api_list: list[dict[str, list[dict[str, str]]]]
        :param cpe_id: cpe identifier
        :type cpe_id: str
        """
        for tr069provision_api in tr069provision_api_list:
            for acs_api, params in tr069provision_api.items():
                api_function = getattr(self, acs_api)
                # To be remvoed once the cpe_id becomes a positional argument for RPCs
                api_fun_with_cpeid = partial(api_function, cpe_id=cpe_id)
                _ = [
                    retry_on_exception(
                        api_fun_with_cpeid,
                        (param,),
                        tout=60,
                        retries=3,
                    )
                    for param in params
                ]

    def _check_axiros_connectivity(self) -> None:
        # a quick connectivity check, this may change
        url = urljoin(self._base_url, "GetListOfCPEs")
        self._client.post(
            url=url,
            json={"CPESearchOptions": {}, "CommandOptions": {}},
            timeout=30,
        ).raise_for_status()
        if self._config.get("ipaddr"):  # we have a console connection
            self._connect()

    @property
    def console(self) -> BoardfarmPexpect:
        """Returns ACS console.

        :return: console
        :rtype: BoardfarmPexpect
        :raises NotSupportedError: if the ACS does not have console access
        """
        if self._console is not None:
            return self._console
        msg = f"{self._config.get('name')} has no console access"
        raise NotSupportedError(msg)

    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        :raises NotSupportedError: if the ACS does not have console access
        """
        if self._console is None:
            msg = f"{self._config.get('name')} has no console access"
            raise NotSupportedError(msg)
        super().delete_file(filename)

    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a local file from a server using SCP.

        :param local_path: local file path
        :param source_path: source path
        :raises NotSupportedError: if the ACS does not have console access
        """
        if self._console is None:
            msg = f"{self._config.get('name')} has no console access"
            raise NotSupportedError(msg)
        super().scp_device_file_to_local(local_path, source_path)

    @property
    def firewall(self) -> IptablesFirewall:
        """Returns Firewall component instance.

        :return: firewall component instance with console object
        :rtype: IptablesFirewall
        :raises NotSupportedError: if the ACS does not have console access
        """
        if self._console is None:
            msg = f"{self._config.get('name')} has no console access"
            raise NotSupportedError(msg)
        if self._firewall is None:
            self._firewall = IptablesFirewall(self._console)
        return self._firewall


AxirosProd = moves.moved_class(AxirosACS, "AxirosProd", __name__)


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template

    AxirosACS(config={}, cmdline_args=Namespace())
