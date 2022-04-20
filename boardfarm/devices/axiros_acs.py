"""Axiros ACS module."""
import ipaddress
import logging
import re
import xml.dom.minidom
from argparse import Namespace
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import xmltodict
import zeep
from nested_lookup import nested_lookup
from requests import HTTPError, Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.cache import InMemoryCache
from zeep.transports import Transport
from zeep.wsse.username import UsernameToken

from boardfarm import hookimpl
from boardfarm.devices.base_devices import LinuxDevice
from boardfarm.exceptions import BoardfarmException, TR069FaultCode, TR069ResponseError
from boardfarm.templates.acs import ACS

_DEFAULT_TIMEOUT = 60 * 2
_LOGGER = logging.getLogger(__name__)


def spa_param_struct(key: str, value: str, _object: Dict) -> Dict[str, Any]:
    """Return the structure of parameters to be passed in SPA.

    This is a helper method used by _build_input_structs function.
    """
    return {
        "Name": key,
        "Notification": value,
        "AccessListChange": _object.get("access_param", "0"),
        "AccessList": _object.get("access_list", []),
        "NotificationChange": _object.get("notification_param", "1"),
    }


class AxirosACS(LinuxDevice, ACS):
    """ACS connection class used to perform TR069 operations."""

    # should the following be dynamic?
    namespaces = {"http://www.w3.org/2001/XMLSchema-instance": None}
    CPE_wait_time = _DEFAULT_TIMEOUT
    Count_retry_on_error = 3  # to be audited
    _cpeid: str = ""

    def __init__(self, config: Dict, cmdline_args: Namespace):
        """Initialize the variable that are used in establishing connection to the ACS and\
           Initialize an HTTP SOAP client which will authenticate with the ACS server.

        :param ``*args``: the arguments to be used if any
        :type ``*args``: tuple
        :param ``**kwargs``: extra args to be used if any
            (mainly contains username, password, ipadress and port)
        :type ``**kwargs``: dict
        """
        super().__init__(config, cmdline_args)
        self._cpeid: str = config.get("cpe_id")
        self._client: Optional[zeep.Client] = None
        if "options" not in self._config:
            return
        for opt in [x.strip() for x in self._config["options"].split(",")]:
            if opt.startswith("wan-static-ipv6:"):
                ipv6_address = opt.replace("wan-static-ipv6:", "").strip()
                if "/" not in opt:
                    ipv6_address += "/64"
                self._ipv6_interface = ipaddress.IPv6Interface(ipv6_address)
                self._gwv6 = self._ipv6_interface.ip

    @hookimpl
    def boardfarm_device_boot(self) -> None:
        """Boardfarm hook implementation to boot ACS device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()
        http_port = self._config.get("http_port", None)
        target = self._ipaddr if http_port is None else self._ipaddr + ":" + http_port
        wsdl = "http://" + target + "/live/CPEManager/DMInterfaces/soap/getWSDL"
        session = Session()
        session.auth = HTTPBasicAuth(
            self._config["http_username"], self._config["http_password"]
        )
        self._client = Client(
            wsdl=wsdl,
            transport=Transport(session=session, cache=InMemoryCache(timeout=3600 * 3)),
            wsse=UsernameToken(
                self._config["http_username"], self._config["http_password"]
            ),
        )

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown ACS device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    # TODO: maybe this could be moved to a lib
    @staticmethod
    def _data_conversion(data: Dict) -> Dict:
        """Conversion type/data helper."""

        def to_int(value: str) -> int:
            return int(value)

        def to_bool(value: str) -> str:
            if value == "1":
                return "true"
            if value == "0":
                return "false"
            return value

        def to_datetime(value: str) -> str:
            if re.search(r"^1\s", value):
                value = value.zfill(len(value) + 3)
            return datetime.strptime(value, "%Y %m %d %H %M %S.0").strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

        conv_table: Dict[str, Dict[str, Optional[Callable]]] = {
            "xsd3:string": {"string": None},
            "xsd3:integer": {"integer": to_int},
            "xsd3:boolean": {"boolean": to_bool},
            "xsd3:ur-type[6]": {"dateTime": to_datetime},
        }
        convdict: Dict = conv_table.get(data["type"])
        if convdict:
            data["type"] = next(iter(convdict))
            if data["value"] != "" and convdict[data["type"]]:
                value = convdict[data["type"]](data["value"])
                data["value"] = value
        return data

    @staticmethod
    def _parse_xml_response(data_values: Union[Dict, List]) -> List[Dict]:
        data_list = []
        if not isinstance(data_values, list):
            data_values = [data_values]
        for data in data_values:
            if "AccessList" in data["value"]:
                access_list = []
                if "item" in data["value"]["AccessList"]:
                    access_list = data["value"]["AccessList"]["item"]["text"]
                data_list.append(
                    {
                        "Name": data["key"]["text"],
                        "AccessList": access_list,
                        "Notification": data["value"]["Notification"]["text"],
                    }
                )
            else:
                value = data["value"].get("text", "")
                if value == "" and "item" in data["value"]:
                    value = " ".join(val.get("text") for val in data["value"]["item"])
                val_type = data["value"]["type"]
                if val_type == "SOAP-ENC:Array":
                    val_type = data["value"][
                        "http://schemas.xmlsoap.org/soap/encoding/:arrayType"
                    ]
                data_list.append(
                    AxirosACS._data_conversion(
                        {"key": data["key"]["text"], "type": val_type, "value": value}
                    )
                )
        return data_list

    @staticmethod
    def _get_xml_key(response: Any, key: str = "text") -> List[Dict]:
        return nested_lookup(
            "Result",
            xmltodict.parse(
                response.content,
                attr_prefix="",
                cdata_key=key,
                process_namespaces=True,
                namespaces=AxirosACS.namespaces,
            ),
        )

    @staticmethod
    def _parse_soap_response(response: Any) -> List[Dict]:
        """Parse the ACS response and return a\
        list of dictionary with {key,type,value} pair."""
        msg = xml.dom.minidom.parseString(response.text)
        _LOGGER.debug(msg.toprettyxml(indent=" ", newl=""))
        result_list = AxirosACS._get_xml_key(response)
        if len(result_list) > 1:
            raise KeyError("More than 1 Result in reply not implemented yet")
        result = result_list[0]
        httpcode = result["code"]["text"]
        msg = result["message"]["text"]
        http_error_message = "HTTP Error code:" + httpcode + " " + msg
        if httpcode != "200":
            # with 507 (timeout/expired) there seem to be NO faultcode message
            if httpcode == "500":
                if "faultcode" not in result["message"]["text"]:
                    raise HTTPError(http_error_message)
            else:
                raise HTTPError(http_error_message)

        # is this needed (might be overkill)?
        if not all(
            [result.get("details"), result.get("message"), result.get("ticketid")]
        ):
            raise TR069ResponseError(
                "ACS malformed response (issues with either "
                "details/message/ticketid)."
            )
        fault = "faultcode" in msg
        if fault:
            # could there be more than 1 fault in a response?
            exc = TR069FaultCode(msg)
            raise exc
        # 'item' is not present in FactoryReset RPC response
        if "item" in result["details"]:
            return AxirosACS._parse_xml_response(result["details"]["item"])
        if (
            "ns1:KeyValueStruct[0]"
            in result["details"]["http://schemas.xmlsoap.org/soap/encoding/:arrayType"]
        ):
            return []
        return []

    def _get_cmd_data(self, *args, **kwagrs) -> Any:  # type: ignore
        # pylint: disable=C0103
        """Return CmdOptTypeStruct_data. It is a helper method."""
        c_opt_type = "ns0:CommandOptionsTypeStruct"
        CmdOptTypeStruct_type = self._client.get_type(c_opt_type)
        return CmdOptTypeStruct_type(*args, **kwagrs)

    def _get_class_data(self, *args, **kwagrs) -> Any:  # type: ignore
        # pylint: disable=C0103
        """Return CPEIdClassStruct_data. It is a helper method."""
        cpe__id_type = "ns0:CPEIdentifierClassStruct"
        CPEIdClassStruct_type = self._client.get_type(cpe__id_type)
        return CPEIdClassStruct_type(*args, **kwagrs)

    def _get_pars_val_data(self, p_arr_type, *args, **kwargs) -> Any:  # type: ignore
        # pylint: disable=C0103
        """Return ParValsParsClassArray_data.It is a helper method."""
        ParValsClassArray_type = self._client.get_type(p_arr_type)
        return ParValsClassArray_type(*args, **kwargs)

    def _build_input_structs(  # noqa: C901
        self, param: Any, action: str, next_level: Optional[bool] = None, **kwargs: Any
    ) -> Tuple:
        # pylint: disable=C0103,R0902,R0914,R0912,R0915
        """Create the get structs used in the get/set param values.

        NOTE: The command option is set as Synchronous

        :param param: parameter to used
        :type param: string or list of strings for get, dict or list of dict for set
        :param action: one of GPV/SPV/GPN/AO/DO/SI/REBOOT/DOWNLOAD
        :param next_level: defaults to null takes True/False
        :return: param_data, cmd_data, cpeid_data
        """
        if action == "SPV":
            if not isinstance(param, list):
                param = [param]  # type: ignore
            list_kv = []
            # this is a list of single k,v pairs
            for _dict in param:
                key = next(iter(_dict))
                list_kv.append({"key": key, "value": _dict[key]})
            p_arr_type = "ns0:SetParameterValuesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, list_kv)
        elif action == "GPV":
            if not isinstance(param, list):
                param = [param]  # type: ignore
            p_arr_type = "ns0:GetParameterValuesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, param)
        elif action == "SPA":
            if not isinstance(param, list):
                param = [param]  # type: ignore
            list_kv = []
            for d in param:
                k = next(iter(d))
                value_list = d[k] if isinstance(d[k], list) else [d[k]]
                for i in value_list:
                    list_kv.append(spa_param_struct(k, i, kwargs))
            p_arr_type = "ns0:SetParameterAttributesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, list_kv)
        elif action == "GPN":
            p_arr_type = "ns0:GetParameterNamesArgumentsStruct"
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, NextLevel=next_level, ParameterPath=param
            )
        elif action == "GPA":
            if not isinstance(param, list):
                param = [param]  # type: ignore
            p_arr_type = "ns0:GetParameterAttributesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, param)
        elif action == "SI":
            if not isinstance(param, list):
                param = [param]  # type: ignore
            p_arr_type = "ns0:ScheduleInformArgumentsStruct"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, *param)
        elif action in ["AO", "DO"]:
            p_arr_type = "ns0:AddDelObjectArgumentsStruct"
            param_key = kwargs.get("param_key", "")
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, param, param_key
            )
        elif action == "REBOOT":
            p_arr_type = "xsd:string"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, param)
        elif action == "DOWNLOAD":
            p_arr_type = "ns0:DownloadArgumentsStruct"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, *param)
        else:
            raise BoardfarmException("Invalid action: " + action)

        sync = kwargs.get("sync", True)
        wait_time = kwargs.get("wait_time", AxirosACS.CPE_wait_time)
        CmdOptTypeStruct_data = self._get_cmd_data(Sync=sync, Lifetime=wait_time)
        CPEIdClassStruct_data = self._get_class_data(cpeid=self._cpeid)
        return ParValsParsClassArray_data, CmdOptTypeStruct_data, CPEIdClassStruct_data

    def GPA(self, param: str) -> List[Dict]:  # pylint: disable=C0103
        """Get parameter attribute of the parameter specified.

        Example usage : acs_server.GPA('Device.WiFi.SSID.1.SSID')

        :param param: parameter to be used in get
        :returns: dictionary with keys Name, AccessList, Notification indicating the GPA
        """
        param_struct, cmd, cpe_id = self._build_input_structs(param, action="GPA")
        with self._client.settings(raw_response=True):
            response = self._client.service.GetParameterAttributes(
                param_struct, cmd, cpe_id
            )
        return AxirosACS._parse_soap_response(response)

    def SPA(  # pylint: disable=C0103
        self, param: Union[List[Dict], Dict], **kwargs: Any
    ) -> List[Dict]:
        """Set parameter attribute of the parameter specified.

        Example usage :

        >>> acs_server.SPA({'Device.WiFi.SSID.1.SSID':'1'}),

        could be parameter list of dicts/dict containing param name and notifications

        :param param: parameter to be used in set
        :param kwargs: access_param,access_list,notification_param
        :returns: SPA response
        """
        param_struct, cmd, cpe_id = self._build_input_structs(
            param, action="SPA", **kwargs
        )
        with self._client.settings(raw_response=True):
            response = self._client.service.SetParameterAttributes(
                param_struct, cmd, cpe_id
            )
        return AxirosACS._parse_soap_response(response)

    def GPV(  # pylint: disable=C0103
        self, param: str, timeout: int = _DEFAULT_TIMEOUT
    ) -> List[Dict]:
        """Get value from CM by ACS for a single given parameter key path synchronously.

        :param param: path to the key that assigned value will be retrieved
        :param timeout: timeout in seconds
        :return: value as a list of dictionary
        """
        param_struct, cmd, cpe_id = self._build_input_structs(
            param, action="GPV", wait_time=timeout
        )
        with self._client.settings(raw_response=True):
            response = self._client.service.GetParameterValues(
                param_struct, cmd, cpe_id
            )
        return AxirosACS._parse_soap_response(response)

    def SPV(  # pylint: disable=C0103
        self, param_value: Dict[str, Any], timeout: int = _DEFAULT_TIMEOUT
    ) -> int:
        """Modify the value of one or more CPE Parameters.

        It can take a single k,v pair or a list of k,v pairs.
        :param param_value: dictionary that contains the path to the key and
        the value to be set. E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :param timeout: to set the Lifetime Expiry time
        :return: status of the SPV as int (0/1)
        :raises: TR069ResponseError if the status is not (0/1)
        """
        param_struct, cmd, cpe_id = self._build_input_structs(
            param_value, action="SPV", wait_time=timeout
        )
        with self._client.settings(raw_response=True):
            response = self._client.service.SetParameterValues(
                param_struct, cmd, cpe_id
            )
        result = AxirosACS._parse_soap_response(response)
        status = int(result[0]["value"])
        if status not in [0, 1]:
            raise TR069ResponseError("SPV Invalid status: " + str(status))
        return status

    def GPN(  # pylint: disable=C0103
        self, param: str, next_level: bool, timeout: int = _DEFAULT_TIMEOUT
    ) -> List[Dict]:
        """Discover the Parameters accessible on a particular CPE.

        :param param: parameter to be discovered
        :param next_level: displays the next level children of the object if marked true
        :param timeout: Lifetime Expiry time
        :return: value as a list of dictionary
        """
        param_struct, cmd, cpe_id = self._build_input_structs(
            param, action="GPN", next_level=next_level, wait_time=timeout
        )
        with self._client.settings(raw_response=True):
            response = self._client.service.GetParameterNames(param_struct, cmd, cpe_id)
        return AxirosACS._parse_soap_response(response)

    def FactoryReset(self) -> List[Dict]:  # pylint: disable=C0103
        """Execute FactoryReset RPC.

        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the Reboot of the device has to be handled in the test.

        :return: factory reset response
        """
        with self._client.settings(raw_response=True):
            response = self._client.service.FactoryReset(
                CommandOptions=self._get_cmd_data(Sync=True, Lifetime=20),
                CPEIdentifier=self._get_class_data(cpeid=self._cpeid),
            )
        return AxirosACS._parse_soap_response(response)

    def Reboot(  # pylint: disable=C0103
        self, command_key: str = "Reboot Test"
    ) -> List[Dict]:
        """Execute Reboot.

        :return: reboot RPC response
        """
        param_struct, cmd, cpe_id = self._build_input_structs(
            command_key, action="REBOOT"
        )
        with self._client.settings(raw_response=True):
            response = self._client.service.Reboot(
                CommandOptions=cmd, CPEIdentifier=cpe_id, Parameters=param_struct
            )

        return AxirosACS._parse_soap_response(response)

    def GetRPCMethods(self) -> List[Dict]:
        # pylint: disable=C0103
        """Execute GetRPCMethods RPC.

        :return: GetRPCMethods response of supported functions
        """
        CmdOptTypeStruct_data = self._get_cmd_data(Sync=True, Lifetime=20)
        CPEIdClassStruct_data = self._get_class_data(cpeid=self._cpeid)
        with self._client.settings(raw_response=True):
            response = self._client.service.GetRPCMethods(
                CommandOptions=CmdOptTypeStruct_data,
                CPEIdentifier=CPEIdClassStruct_data,
            )
        return AxirosACS._parse_soap_response(response)
