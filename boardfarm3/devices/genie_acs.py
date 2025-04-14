"""GenieACS module."""

from __future__ import annotations

import logging
from argparse import Namespace
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urljoin

import httpx
from typing_extensions import LiteralString

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import (
    BoardfarmException,
    ContingencyCheckError,
    NotSupportedError,
)
from boardfarm3.lib.utils import retry_on_exception
from boardfarm3.templates.acs import ACS, GpvInput, GpvResponse, SpvInput
from boardfarm3.templates.cpe.cpe import CPE

if TYPE_CHECKING:
    from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
    from boardfarm3.lib.device_manager import DeviceManager
    from boardfarm3.lib.networking import IptablesFirewall

_DEFAULT_TIMEOUT = 60 * 2
_LOGGER = logging.getLogger(__name__)


# pylint:disable=R0801,too-many-public-methods
class GenieACS(LinuxDevice, ACS):
    """GenieACS connection class used to perform TR-069 operations."""

    CPE_wait_time = _DEFAULT_TIMEOUT

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize the variables that are used in establishing connection to the ACS.

        :param config: Boardfarm config
        :type config: dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        self._disable_log_messages_from_libraries()
        super().__init__(config, cmdline_args)
        self._client: httpx.Client | None = None
        self._cpeid: str | None = None
        self._base_url: str | None = None

    def _disable_log_messages_from_libraries(self) -> None:
        """Disable logs from httpx."""
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    def _init_nbi_client(self) -> None:
        if self._client is None:
            self._base_url = (
                f"http://{self.config.get('ipaddr')}:{self.config.get('http_port')}"
            )
            self._client = httpx.Client(
                auth=(
                    self.config.get("http_username", "admin"),
                    self.config.get("http_password", "admin"),
                ),
            )
            try:
                # do a request to test the connection
                self._request_get("/files")
            except (httpx.ConnectError, httpx.HTTPError) as exc:
                raise ConnectionError from exc

    def _request_get(
        self,
        endpoint: str,
        timeout: int | None = CPE_wait_time,
    ) -> Any:  # noqa: ANN401
        request_url = urljoin(self._base_url, endpoint)
        try:
            response = self._client.get(request_url, timeout=timeout)
            response.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPError) as exc:
            raise ConnectionError from exc
        return response.json()

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to skip boot the ITCProvisioner."""
        _LOGGER.info(
            "Initializing %s(%s) device with skip-boot option",
            self.device_name,
            self.device_type,
        )
        self._connect()
        self._init_nbi_client()

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot the ITCProvisioner."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        self._init_nbi_client()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown ACS device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()
        self._client.close()

    # FIXME:I'm not a booting hook and I don't belong here!  # noqa: FIX001
    # BOARDFARM-4920
    @hookimpl
    def contingency_check(self, env_req: dict[str, Any]) -> None:
        """Make sure ACS is able to read CPE/TR069 client params.

        :param env_req: test env request
        :type env_req: dict[str, Any]
        :raises ContingencyCheckError: if CPE is not registered to ACS.
        """
        if self._cmdline_args.skip_contingency_checks or "tr-069" not in env_req.get(
            "environment_def",
            {},
        ):
            return
        _LOGGER.info("Contingency check %s(%s)", self.device_name, self.device_type)
        if not bool(
            retry_on_exception(
                self.GPV,
                ("Device.DeviceInfo.SoftwareVersion",),
                retries=10,
                tout=30,
            ),
        ):
            msg = "ACS service check Failed."
            raise ContingencyCheckError(msg)

    @property
    def url(self) -> str:
        """Returns acs url used.

        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def GPA(self, param: str, cpe_id: str | None = None) -> list[dict]:
        """Execute GetParameterAttributes RPC call for the specified parameter.

        Example usage:

        >>> acs_server.GPA("Device.WiFi.SSID.1.SSID")

        :param param: parameter to be used in get
        :type param: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def SPA(
        self,
        param: list[dict] | dict,
        notification_param: bool = True,
        access_param: bool = False,
        access_list: list | None = None,
        cpe_id: str | None = None,
    ) -> list[dict]:
        """Execute SetParameterAttributes RPC call for the specified parameter.

        Example usage:

        >>> (acs_server.SPA({"Device.WiFi.SSID.1.SSID": "1"}),)

        could be parameter list of dicts/dict containing param name and notifications

        :param param: parameter as key of dictionary and notification as its value
        :type param: list[dict] | dict
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
        :type access_list: list | None, optional
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def _build_input_structs(self, param: str | list[str]) -> str:
        return param if isinstance(param, str) else ",".join(param)

    def _flatten_dict(
        self,
        nested_dictionary: dict,
        parent_key: str = "",
        sep: str = ".",
    ) -> dict[Any, Any]:
        items: list = []
        for key, value in nested_dictionary.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(self._flatten_dict(value, new_key, sep=sep).items())
            else:
                items.append((new_key, value))
        return dict(items)

    def _convert_to_string(self, data: Any) -> LiteralString:  # noqa: ANN401
        flattened_dict = self._flatten_dict(data)
        result = []
        for key, value in flattened_dict.items():
            if "_value" in key:
                result.append(
                    f"{key.strip('._value')}, {value}, "
                    f"{flattened_dict[key.replace('_value', '_type')]}",
                )
        return ", ".join(result)

    def _convert_response(
        self,
        response_data: Any,  # noqa: ANN401
    ) -> list[dict[str, Any]]:
        elements = self._convert_to_string(response_data[0]).split(", ")
        return [
            dict(zip(("key", "value", "type"), elements[i : i + 3]))
            for i in range(0, len(elements), 3)
        ]

    def GPV(
        self,
        param: GpvInput,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> GpvResponse:
        """Send GetParamaterValues command via ACS server.

        :param param: TR069 parameters to get values of
        :type param: GpvInput
        :param timeout: wait time for the RPC to complete, defaults to None
        :type timeout: int | None, optional
        :param cpe_id: CPE identifier, defaults to None
        :type cpe_id: str | None, optional
        :return: GPV response with keys, value and datatype
        :rtype: GpvResponse
        """
        cpe_id = cpe_id if cpe_id else self._cpeid
        quoted_id = quote('{"_id":"' + cpe_id + '"}', safe="")
        self._request_post(
            endpoint="/devices/" + quote(cpe_id) + "/tasks",
            data=self._build_input_structs_gpv(param),
            conn_request=True,
            timeout=timeout,
        )
        response_data = self._request_get(
            "/devices"  # noqa: ISC003
            + "?query="
            + quoted_id
            + "&projection="
            + self._build_input_structs(param),
            timeout=timeout,
        )
        return GpvResponse(self._convert_response(response_data))

    def _build_input_structs_gpv(self, param_value: str | list[str]) -> dict[str, Any]:
        if isinstance(param_value, list):
            return {"name": "getParameterValues", "parameterNames": param_value}
        return {"name": "getParameterValues", "parameterNames": [param_value]}

    def _build_input_structs_spv(
        self,
        param_value: dict[str, Any] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        data = []
        for spv_params in param_value:
            if isinstance(spv_params, dict):
                data.append(
                    [
                        f"{iter(spv_params.keys())}",
                        iter(spv_params.values()),
                    ],
                )
            elif isinstance(spv_params, str) and isinstance(param_value, dict):
                data.append([spv_params, param_value[spv_params]])
        return {"name": "setParameterValues", "parameterValues": data}

    def _request_post(
        self,
        endpoint: str,
        data: dict[str, Any] | list[Any],
        conn_request: bool = True,
        timeout: int | None = None,
    ) -> Any:  # noqa: ANN401
        if conn_request:
            request_url = urljoin(self._base_url, f"{endpoint}?connection_request")
        else:
            err_msg = (
                "It is unclear how the code would work without 'conn_request' "
                "being True. /FC"
            )
            raise ValueError(err_msg)
        try:
            timeout = timeout if timeout else GenieACS.CPE_wait_time
            response = self._client.post(request_url, json=data, timeout=timeout)
            response.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPError) as exc:
            raise ConnectionError from exc
        return response.json()

    def SPV(
        self,
        param_value: SpvInput,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> int:
        """Execute SetParameterValues RPC call for the specified parameter.

        :param param_value: dictionary that contains the path to the key and
            the value to be set. Example:
            .. code-block:: python

                {"Device.WiFi.AccessPoint.1.AC.1.Alias": "mok_1"}

        :type param_value: SpvInput
        :param timeout: wait time for the RPC to complete, defaults to None
        :type timeout: int | None
        :param cpe_id: CPE identifier, defaults to None
        :type cpe_id: str | None
        :return: status of the SPV, either 0 or 1
        :rtype: int
        """
        cpe_id = cpe_id if cpe_id else self._cpeid
        spv_data = self._build_input_structs_spv(param_value)
        response_data = self._request_post(
            endpoint="/devices/" + quote(cpe_id) + "/tasks",
            data=spv_data,
            conn_request=True,
            timeout=timeout,
        )
        return bool(response_data)

    def FactoryReset(self, cpe_id: str | None = None) -> list[dict]:
        """Execute FactoryReset RPC.

        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the reboot of the device has to be handled in the test.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def Reboot(self, CommandKey: str, cpe_id: str | None = None) -> list[dict]:
        """Execute Reboot RPC.

        :param CommandKey: reboot command key
        :type CommandKey: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def AddObject(
        self,
        param: str,
        param_key: str = "",
        cpe_id: str | None = None,
    ) -> list[dict]:
        """Execute AddOjbect RPC call for the specified parameter.

        :param param: parameter to be used to add
        :type param: str
        :param param_key: the value to set the ParameterKey parameter, defaults to ""
        :type param_key: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def DelObject(
        self,
        param: str,
        param_key: str = "",
        cpe_id: str | None = None,
    ) -> list[dict]:
        """Execute DeleteObject RPC call for the specified parameter.

        :param param: parameter to be used to delete
        :type param: str
        :param param_key: the value to set the ParameterKey parameter, defaults to ""
        :type param_key: str
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def GPN(
        self,
        param: str,
        next_level: bool,
        timeout: int | None = None,
        cpe_id: str | None = None,
    ) -> list[dict]:
        """Execute GetParameterNames RPC call for the specified parameter.

        :param param: parameter to be discovered
        :type param: str
        :param next_level: displays the next level children of the object if marked true
        :type next_level: bool
        :param timeout: Lifetime Expiry time
        :type timeout: int | None
        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def ScheduleInform(
        self,
        CommandKey: str = "Test",
        DelaySeconds: int = 20,
        cpe_id: str | None = None,
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
        :type cpe_id: str | None, optional
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def GetRPCMethods(self, cpe_id: str | None = None) -> list[dict]:
        """Execute GetRPCMethods RPC.

        :param cpe_id: cpe identifier, defaults to None
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

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
        :type cpe_id: str | None
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

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
        cpe_id = cpe_id if (cpe_id == self._cpeid) else self._cpeid
        for tr069provision_api in tr069provision_api_list:
            for acs_api, params in tr069provision_api.items():
                api_function = getattr(self, acs_api)
                _ = [
                    retry_on_exception(
                        api_function,
                        (param, 30, cpe_id),
                        tout=60,
                        retries=3,
                    )
                    for param in params
                ]

    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a local file from a server using SCP.

        :param local_path: local file path
        :param source_path: source path
        :raises NotImplementedError: missing implementation
        """
        raise NotImplementedError

    # TODO: This hack has to be done to make skip-boot a separate flow
    # The solution should be removed in the future and should not build upon
    def _add_cpe_id_to_acs_device(self, device_manager: DeviceManager) -> None:
        cpe = device_manager.get_device_by_type(CPE)  # type: ignore[type-abstract]
        if (
            not (oui := cpe.config.get("oui"))
            or not (product_class := cpe.config.get("product_class"))
            or not (serial := cpe.config.get("serial"))
        ):
            err_msg = "Inventory needs to have oui, product_class and serial entries!"
            raise BoardfarmException(err_msg)
        self._cpeid = f"{oui}-{product_class}-{serial}"

    @property
    def console(self) -> BoardfarmPexpect:
        """Returns ACS console.

        :raises NotSupportedError: does not support SSH
        """
        raise NotSupportedError

    @property
    def firewall(self) -> IptablesFirewall:
        """Returns Firewall iptables instance.

        :raises NotSupportedError: does not support Firewall
        """
        raise NotSupportedError


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template
    GenieACS(config={}, cmdline_args=Namespace())
