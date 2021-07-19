import ast
import inspect
import ipaddress
import logging
import os
import re
import time
import warnings
import xml.dom.minidom
from datetime import datetime
from xml.etree import ElementTree

import pexpect
import xmltodict
from debtcollector import moves
from nested_lookup import nested_lookup
from requests import HTTPError, Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.cache import InMemoryCache
from zeep.transports import Transport
from zeep.wsse.username import UsernameToken

from boardfarm.exceptions import (
    ACSFaultCode,
    CodeError,
    TR069FaultCode,
    TR069ResponseError,
)
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from boardfarm.lib.common import get_class_name_in_stack, scp_from
from boardfarm.lib.dns import DNS
from boardfarm.lib.network_testing import kill_process, tcpdump_capture

from . import base_acs

warnings.simplefilter("always", UserWarning)

logger = logging.getLogger("zeep.transports")


default_timeout = 60 * 2


class Intercept:
    """Any calls on Axiros RPC functions "GPV","SPV", "GPA","GPN", "SPA","AddObject","DelObject","FactoryReset","Reboot","ScheduleInform","GetRPCMethods","Download" will capture tcpdump if the ssh session is connected.
    And also adds a wait time of 10 seconds when 507 HTTPError is thrown.
    """

    __dump_on = [
        "GPV",
        "SPV",
        "GPA",
        "SPA",
        "GPN",
        "AddObject",
        "DelObject",
        "FactoryReset",
        "Reboot",
        "ScheduleInform",
        "GetRPCMethods",
        "Download",
    ]

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        if callable(attr):
            d_flag = False
            if name in Intercept.__dump_on and self.session_connected:
                # sets the flag to true only if ssh session is connected
                d_flag = True

            def newfunc(*args, **kwargs):
                count = 2  # retries on 507 HTTPerror, even if ssh conn is not available
                if d_flag:
                    arg = [x for x in args]
                    if (
                        args
                        and hasattr(self.dev.board, "unsupported_objects")
                        and arg[0] in self.dev.board.unsupported_objects
                    ):
                        warnings.warn("Unsupported parameter")
                        logger.warning("Warning!!! Unsupported parameter")
                        return
                    stack = inspect.stack()
                    build_number = os.getenv("BUILD_NUMBER", "")
                    job_name = os.getenv("JOB_NAME", "")
                    pcap = "_" + time.strftime("%Y%m%d_%H%M%S") + ".pcap"
                    capture = (
                        job_name.replace("/", "_")
                        + "_"
                        + build_number
                        + "_"
                        + (
                            get_class_name_in_stack(
                                self,
                                ["test_main", "mvx_tst_setup"],
                                stack,
                                not_found="TestNameNotFound",
                            )
                            + pcap
                        )
                    )
                ok = False
                for retry in range(count):
                    result = None
                    if d_flag:
                        tcpdump_output = tcpdump_capture(
                            self,
                            "any",
                            capture_file=capture,
                            return_pid=True,
                            additional_filters=self.tcpdump_filter,
                        )
                    try:
                        result = attr(*args, **kwargs)
                        ok = True  # will remove file in finally
                        break
                    except Exception as e:
                        if "507" not in str(e):
                            raise (e)
                        else:
                            if retry != (count - 1):
                                # adding 10 sec timeout
                                warnings.warn(
                                    "Ten seconds of timeout is added to compensate DOS attack."
                                )
                                self.expect(pexpect.TIMEOUT, timeout=10)
                            else:
                                raise (e)
                    finally:
                        # kill and if successful remove pcap file
                        if d_flag:
                            kill_process(
                                self,
                                process="tcpdump",
                                pid=tcpdump_output,
                                sync=False,
                            )
                            if not ok and (retry == (count - 1)):
                                logger.info(
                                    "\x1b[6;30;42m"
                                    + f"TCPdump is saved in {capture}"
                                    + "\x1b[0m"
                                )
                                # captured packet is moved to results folder
                                dest = os.path.realpath("results")
                                scp_from(
                                    capture,
                                    self.ipaddr,
                                    self.cli_username,
                                    self.cli_password,
                                    self.cli_port,
                                    dest,
                                )
                            self.sendline(f"rm {capture}")
                            self.expect(self.prompt)

                return result

            return newfunc
        else:
            return attr


class AxirosACS(Intercept, base_acs.BaseACS):
    """ACS connection class used to perform TR069 operations on stations/board."""

    model = "axiros_acs_soap"
    name = "acs_server"
    # should the following be dynamic?
    namespaces = {"http://www.w3.org/2001/XMLSchema-instance": None}
    CPE_wait_time = default_timeout
    Count_retry_on_error = 3  # to be audited

    def __init__(self, *args, **kwargs):
        """Initialize the variable that are used in establishing connection to the ACS and\
           Initialize an HTTP SOAP client which will authenticate with the ACS server.

        :param ``*args``: the arguments to be used if any
        :type ``*args``: tuple
        :param ``**kwargs``: extra args to be used if any (mainly contains username, password, ipadress and port)
        :type ``**kwargs``: dict
        """
        self.args = args
        self.kwargs = kwargs
        self.username = self.kwargs["username"]
        self.password = self.kwargs["password"]
        self.ipaddr = self.kwargs["ipaddr"]
        self.port = self.kwargs.get("port", None)
        self.cli_port = self.kwargs.pop("cli_port", "22")
        self.cli_username = self.kwargs.pop("cli_username", None)
        self.cli_password = self.kwargs.pop("cli_password", None)
        self.color = self.kwargs.pop("color", None)
        self.options = self.kwargs.pop("options", None)
        self.aux_ip = self.kwargs.pop("aux_ip", None)
        self.aux_url = self.kwargs.pop("aux_url", None)
        self.tcpdump_filter = ""
        AxirosACS.CPE_wait_time = self.kwargs.pop("wait_time", AxirosACS.CPE_wait_time)

        if self.options:
            options = [x.strip() for x in self.options.split(",")]
            for opt in options:
                if opt.startswith("wan-static-ipv6:"):
                    ipv6_address = opt.replace("wan-static-ipv6:", "").strip()
                    if "/" not in opt:
                        ipv6_address += "/64"
                    self.ipv6_interface = ipaddress.IPv6Interface(ipv6_address)
                    self.gwv6 = self.ipv6_interface.ip

        target = self.ipaddr if self.port is None else self.ipaddr + ":" + self.port
        self.wsdl = "http://" + target + "/live/CPEManager/DMInterfaces/soap/getWSDL"

        session = Session()
        session.auth = HTTPBasicAuth(self.username, self.password)

        self.client = Client(
            wsdl=self.wsdl,
            transport=Transport(session=session, cache=InMemoryCache(timeout=3600 * 3)),
            wsse=UsernameToken(self.username, self.password),
        )

        # to spawn pexpect on cli
        self.session_connected = False
        if all([self.ipaddr, self.cli_username, self.cli_password]):
            bft_pexpect_helper.spawn.__init__(
                self,
                command="ssh",
                args=[
                    f"{self.cli_username}@{self.ipaddr}",
                    "-p",
                    self.cli_port,
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "ServerAliveInterval=60",
                    "-o",
                    "ServerAliveCountMax=5",
                ],
            )
            self.check_connection(self.cli_username, self.name, self.cli_password)
            self.print_connected_console_msg(
                self.ipaddr, self.cli_port, self.color, self.name
            )
            self.session_connected = True

        # this should be populater ONLY when using __main__
        self.cpeid = self.kwargs.pop("cpeid", None)
        self.dns = DNS(self, self.options, self.aux_ip, self.aux_url)

    def sudo_sendline(self, cmd):
        # overwriting linux behaviour
        # this is under assumption that acs is having root credentials.
        self.sendline(cmd)

    def __str__(self):
        """Format the string representation of self object (instance).

        :returns: :class:`Response <Response>` string representation of self object.
        :rtype: string
        """
        return "AxirosACS"

    # TO DO: maybe this could be moved to a lib
    @staticmethod
    def _data_conversion(d):
        """Conversion type/data helper."""

        def to_int(v):
            return int(v)

        def to_bool(v):
            if v == "1":
                return "true"
            elif v == "0":
                return "false"
            return v

        def to_dateTime(v):
            if re.search(r"^1\s", v):
                v = v.zfill(len(v) + 3)
            v = datetime.strptime(v, "%Y %m %d %H %M %S.0").strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            return v

        conv_table = {
            "xsd3:string": {"string": None},
            "xsd3:integer": {"integer": to_int},
            "xsd3:boolean": {"boolean": to_bool},
            "xsd3:ur-type[6]": {"dateTime": to_dateTime},
        }
        convdict = conv_table.get(d["type"])
        if convdict:
            d["type"] = next(iter(convdict))
            if d["value"] != "" and convdict[d["type"]]:
                v = convdict[d["type"]](d["value"])
                d["value"] = v
        return d

    @staticmethod
    def _parse_xml_response(data_values):
        data_list = []
        if type(data_values) is not list:
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
                v = data["value"].get("text", "")
                if v == "" and "item" in data["value"]:
                    v = " ".join(val.get("text") for val in data["value"]["item"])
                val_type = data["value"]["type"]
                if val_type == "SOAP-ENC:Array":
                    val_type = data["value"][
                        "http://schemas.xmlsoap.org/soap/encoding/:arrayType"
                    ]
                data_list.append(
                    AxirosACS._data_conversion(
                        {"key": data["key"]["text"], "type": val_type, "value": v}
                    )
                )

        return data_list

    @staticmethod
    def _get_xml_key(resp, k="text"):
        return nested_lookup(
            "Result",
            xmltodict.parse(
                resp.content,
                attr_prefix="",
                cdata_key=k,
                process_namespaces=True,
                namespaces=AxirosACS.namespaces,
            ),
        )

    @staticmethod
    def _parse_soap_response(response):
        """Parse the ACS response and return a\
        list of dictionary with {key,type,value} pair."""
        msg = xml.dom.minidom.parseString(response.text)
        logger.debug(msg.toprettyxml(indent=" ", newl=""))

        result = AxirosACS._get_xml_key(response)
        if len(result) > 1:
            raise KeyError("More than 1 Result in reply not implemented yet")
        result = result[0]
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
            e = TR069ResponseError(
                "ACS malformed response (issues with either "
                "details/message/ticketid)."
            )
            e.result = result  # for inspection later
            raise e
        fault = "faultcode" in msg
        if fault:
            # could there be more than 1 fault in a response?
            e = TR069FaultCode(msg)
            e.faultdict = ast.literal_eval(msg[msg.index("{") :])
            raise e
        # 'item' is not present in FactoryReset RPC response
        if "item" in result["details"]:
            return AxirosACS._parse_xml_response(result["details"]["item"])
        elif (
            "ns1:KeyValueStruct[0]"
            in result["details"]["http://schemas.xmlsoap.org/soap/encoding/:arrayType"]
        ):
            return []

    def _get_cmd_data(self, *args, **kwagrs):
        """Return CmdOptTypeStruct_data. It is a helper method."""
        c_opt_type = "ns0:CommandOptionsTypeStruct"
        CmdOptTypeStruct_type = self.client.get_type(c_opt_type)
        return CmdOptTypeStruct_type(*args, **kwagrs)

    def _get_class_data(self, *args, **kwagrs):
        """Return CPEIdClassStruct_data. It is a helper method."""
        cpe__id_type = "ns0:CPEIdentifierClassStruct"
        CPEIdClassStruct_type = self.client.get_type(cpe__id_type)
        return CPEIdClassStruct_type(*args, **kwagrs)

    def _get_pars_val_data(self, p_arr_type, *args, **kwargs):
        """Return ParValsParsClassArray_data.It is a helper method."""
        ParValsClassArray_type = self.client.get_type(p_arr_type)
        return ParValsClassArray_type(*args, **kwargs)

    def spa_param_struct(self, k, v, o):
        """Returns the structure of parameters to be passed in SPA
        This is a helper method used by _build_input_structs function"""
        return {
            "Name": k,
            "Notification": v,
            "AccessListChange": o.get("access_param", "0"),
            "AccessList": o.get("access_list", []),
            "NotificationChange": o.get("notification_param", "1"),
        }

    def _build_input_structs(self, cpeid, param, action, next_level=None, **kwargs):
        """Helper function to create the get structs used in the get/set param values

        NOTE: The command option is set as Synchronous
        :param cpeid: the serial number of the modem through which ACS communication
        happens.
        :type cpeid: string
        :param param: parameter to used
        :type param: string or list of strings for get, dict or list of dict for set
        :param action: one of GPV/SPV/GPN/AO/DO/SI/REBOOT/DOWNLOAD
        :type action: string
        :param next_level: defaults to null takes True/False
        :type next_level: boolean
        :raises: NA
        :returns: param_data, cmd_data, cpeid_data
        """
        if action == "SPV":
            if type(param) is not list:
                param = [param]
            list_kv = []
            # this is a list of single k,v pairs
            for d in param:
                k = next(iter(d))
                list_kv.append({"key": k, "value": d[k]})
            p_arr_type = "ns0:SetParameterValuesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, list_kv)

        elif action == "GPV":
            if type(param) is not list:
                param = [param]
            p_arr_type = "ns0:GetParameterValuesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, param)

        elif action == "SPA":
            if type(param) is not list:
                param = [param]
            list_kv = []
            for d in param:
                k = next(iter(d))
                value_list = d[k] if type(d[k]) is list else [d[k]]
                for i in value_list:
                    list_kv.append(self.spa_param_struct(k, i, kwargs))
            p_arr_type = "ns0:SetParameterAttributesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, list_kv)

        elif action == "GPN":

            p_arr_type = "ns0:GetParameterNamesArgumentsStruct"
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, NextLevel=next_level, ParameterPath=param
            )

        elif action == "GPA":
            if type(param) is not list:
                param = [param]
            p_arr_type = "ns0:GetParameterAttributesParametersClassArray"
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, param)

        elif action == "SI":
            if type(param) is not list:
                param = [param]
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
            raise CodeError("Invalid action: " + action)

        sync = kwargs.get("sync", True)
        wait_time = kwargs.get("wait_time", AxirosACS.CPE_wait_time)

        CmdOptTypeStruct_data = self._get_cmd_data(Sync=sync, Lifetime=wait_time)

        CPEIdClassStruct_data = self._get_class_data(cpeid=cpeid)

        return ParValsParsClassArray_data, CmdOptTypeStruct_data, CPEIdClassStruct_data

    def close(self):
        """Implement to close ACS connection. TODO."""
        pass

    def get_ticketId(self, cpeid, param):
        """ACS server maintain a ticket ID for all TR069 RPC calls.

        This method will construct a TR069 GPV query, execute it and
        return the ticket id associated with it.

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to used
        :type param: string
        :raises: NA
        :returns: ticketid
        :rtype: string
        """
        GetParameterValuesParametersClassArray_type = self.client.get_type(
            "ns0:GetParameterValuesParametersClassArray"
        )
        GetParameterValuesParametersClassArray_data = (
            GetParameterValuesParametersClassArray_type([param])
        )

        CommandOptionsTypeStruct_type = self.client.get_type(
            "ns0:CommandOptionsTypeStruct"
        )
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            "ns0:CPEIdentifierClassStruct"
        )
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.GetParameterValues(
                GetParameterValuesParametersClassArray_data,
                CommandOptionsTypeStruct_data,
                CPEIdentifierClassStruct_data,
            )

        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter("ticketid"):
            ticketid = value.text
            break
        return ticketid

    @moves.moved_method("GPV")
    def get(self, cpeid, param, wait=8):
        """Perform a remote procedure call (GetParameterValue).

        This method is deprecated.
        The method will query the ACS server for value against ticket_id generated
        during the GPV RPC call.
        Example usage : acs_server.get(self.cpeid, 'Device.DeviceInfo.SoftwareVersion')

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used in get
        :type param: string
        :param wait: the number of tries to be done if we are not getting proper ACS response, defaults to 8
        :type wait: int
        :raises: NA
        :returns: first value of ACS response for the parameter.
        :rtype: string
        """
        try:
            return self.GPV(param)[0]["value"]
        except Exception as e:
            logger.error(e)
            return None

    @moves.moved_method("GPV")
    def getcurrent(self, cpeid, param, wait=8):
        """Get the key, value of the response for the given parameter from board.

        Example usage : acs_server.getcurrent(self.cpeid, 'Device.IP.Interface.')
        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used in get
        :type param: string
        :param wait: the number of tries to be done if we are not getting proper ACS response, defaults to 8
        :type wait: int
        :raises: NA
        :returns: dictionary with the key, value of the response for the given parameter.
        :rtype: dict
        """
        try:
            out = self.GPV(param)
            return {item["key"]: item["value"] for item in out}
        except Exception as e:
            logger.error(e)
            return {}

    @moves.moved_method("SPV")
    def set(self, cpeid, attr, value):
        """Set a parameter in board via TR069 RPC call (SetParameterValue).

        This method constructs a SPV query and sends it to ACS server
        ACS server will generate a ticket_id and perform the RPC call.
        The method will then return the value associated with the ticket_id
        Example usage : acs_server.set(self.cpeid, 'Device.WiFi.AccessPoint.1.AC.1.Alias', "TestSSID")

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param attr: attribute to be used to set
        :type attr: string
        :param values: the value to be set to the attr
        :type values: string
        :raises: NA
        :returns: ticketId for set.
        :rtype: string
        """
        try:
            param = {attr: value}
            return str(self.SPV(param))
        except Exception as e:
            print(e)
            return None

    def Axiros_GetListOfCPEs(self):
        """Get the list of all devices registered on the ACS server.

        :raises: NA
        :returns: ACS response containing the list of CPE.
        :rtype: string
        """
        CPESearchOptionsClassStruct_type = self.client.get_type(
            "ns0:CPESearchOptionsClassStruct"
        )
        CPESearchOptionsClassStruct_data = CPESearchOptionsClassStruct_type()

        CommandOptionsForCPESearchStruct_type = self.client.get_type(
            "ns0:CommandOptionsForCPESearchStruct"
        )
        CommandOptionsForCPESearchStruct_data = CommandOptionsForCPESearchStruct_type()

        response = self.client.service.GetListOfCPEs(
            CPESearchOptionsClassStruct_data, CommandOptionsForCPESearchStruct_data
        )
        if response["code"] != 200:
            return None

        return response

    def Axiros_DeleteCPEs(self, cpeid):
        """Delete a CPE on the ACS server.

        :raises: NA
        :returns: True if successful
        :rtype: True/False
        """
        CPESearchOptionsClassStruct_type = self.client.get_type(
            "ns0:CPESearchOptionsClassStruct"
        )
        CPESearchOptionsClassStruct_data = CPESearchOptionsClassStruct_type(cpeid=cpeid)

        CommandOptionsForCPESearchStruct_type = self.client.get_type(
            "ns0:CommandOptionsForCPESearchStruct"
        )
        CommandOptionsForCPESearchStruct_data = CommandOptionsForCPESearchStruct_type()

        response = self.client.service.DeleteCPEs(
            CPESearchOptionsClassStruct_data, CommandOptionsForCPESearchStruct_data
        )
        print(response)
        return response["code"] == 200

    delete_cpe = Axiros_DeleteCPEs

    def Axiros_GetTicketResponse(self, ticketid):
        """Get the ticket response on ACS.

        :param ticketid: the ticketid to be used to get the ACS response.
        :type ticketid: string
        :raises: NA
        :returns: ACS response.
        :rtype: string
        """
        response = self.client.service.get_generic_sb_result(ticketid)

        if response["code"] != 200:
            return None

        return response["code"]

    def Axiros_GetTicketValue(self, ticketid, wait=8, objtype=False):
        """Get the text of ticket response on ACS.

        :param ticketid: the ticketid to be used to get the ACS response.
        :type ticketid: string
        :param wait: the number of tries to be done if we are not getting proper ACS response, defaults to 8
        :type wait: int
        :param objtype: to get object's data type this flag must be true; defaults to false
        :type objtype: boolean
        :raises: ACSFaultCode
        :returns: ACS response text / None.
        :rtype: string/None
        """
        for _ in range(wait):
            time.sleep(1)
            with self.client.settings(raw_response=True):
                ticket_resp = self.client.service.get_generic_sb_result(ticketid)

            root = ElementTree.fromstring(ticket_resp.content)
            for _value in root.iter("code"):
                break
            if _value.text != "200":
                for message in root.iter("message"):
                    if message.text and "faultcode" in message.text:
                        raise ACSFaultCode(message.text)
                    break
                continue
            for value in root.iter("value"):
                if all([objtype, value.text]):
                    for key, object_type in value.attrib.items():
                        if "type" in key:
                            return object_type.split(":")[1]
                else:
                    return value.text
        return None

    def GPA(self, param):
        """Get parameter attribute on ACS of the parameter specified i.e a remote procedure call (GetParameterAttribute).

        Example usage : acs_server.GPA('Device.WiFi.SSID.1.SSID')
        :param param: parameter to be used in get
        :type param: string
        :returns: dictionary with keys Name, AccessList, Notification indicating the GPA
        :rtype: dict
        """

        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(self.cpeid, param, action="GPA")

        with self.client.settings(raw_response=True):
            response = self.client.service.GetParameterAttributes(p, cmd, cpe_id)
        return AxirosACS._parse_soap_response(response)

    @moves.moved_method("GPA")
    def rpc_GetParameterAttributes(self, cpeid, param):
        """Get parameter attribute on ACS of the parameter specified i.e a remote procedure call (GetParameterAttribute).

        Example usage : acs_server.rpc_GetParameterAttributes('DEAP815610DA', 'Device.WiFi.SSID.1.SSID')
        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used in get
        :type param: string
        :raises: NA
        :returns: dictionary with keys Name, Notification (0/1), AccessList indicating the GPA
        :rtype: dict
        """
        try:
            return self.GPA(param)

        except Exception as e:
            logger.error(e)
            return {}

    @moves.moved_method("SPA")
    def rpc_SetParameterAttributes(self, cpeid, attr, value):
        """Set parameter attribute on ACS of the parameter specified i.e a remote procedure call (SetParameterAttribute).

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param attr: attribute to be used to set
        :type attr: string
        :param values: the value to be set to the attr
        :type values: string
        :raises: NA
        :returns: ticket response on ACS.
        :rtype: string
        """
        try:
            param = {attr: value}
            return self.SPA(param)
        except Exception as e:
            logger.error(e)
            return None

    def SPA(self, param, **kwargs):
        """Get parameter attribute on ACS of the parameter specified i.e a remote procedure call (GetParameterAttribute).

        Example usage : acs_server.SPA({'Device.WiFi.SSID.1.SSID':'1'}),could be parameter list of dicts/dict containing param name and notifications
        :param param: parameter to be used in set
        :type param: List of Dictionary or Dictionary
        :param kwargs : access_param,access_list,notification_param
        :returns: SPA response
        :rtype: dict
        """

        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(
            self.cpeid, param, action="SPA", **kwargs
        )

        with self.client.settings(raw_response=True):
            response = self.client.service.SetParameterAttributes(p, cmd, cpe_id)
        return AxirosACS._parse_soap_response(response)

    @moves.moved_method("AddObject")
    def rpc_AddObject(self, cpeid, param, **kwargs):
        """Add object ACS of the parameter specified i.e a remote procedure call (AddObject).

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used to add
        :type param: string
        :param kwargs : param_key (parameterkey to set), wait (wait to retry)
        :raises assertion: rpc_AddObject failed to lookup for the param
        :returns: ticket response on ACS
        :rtype: dictionary
        """
        # setting no of tries default to 8
        if kwargs.get("wait", None) is None:
            kwargs["wait"] = 8

        return {i["key"]: i["value"] for i in self.AddObject(param, **kwargs)}

    def AddObject(self, param, **kwargs):
        """Add object ACS of the parameter specified i.e a remote procedure call (AddObject).

        :param param: parameter to be used to add
        :type param: string
        :param kwargs : param_key
        :raises assertion: On failure
        :returns: list of dictionary with key, value, type indicating the AddObject
        :rtype: dictionary
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid
        p, cmd, cpe_id = self._build_input_structs(
            self.cpeid, param, action="AO", **kwargs
        )

        # get raw soap response
        with self.client.settings(raw_response=True):
            response = self.client.service.AddObject(p, cmd, cpe_id)

        return AxirosACS._parse_soap_response(response)

    @moves.moved_method("DelObject")
    def rpc_DelObject(self, cpeid, param, **kwargs):
        """Delete object ACS of the parameter specified i.e a remote procedure call (DeleteObject).

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used to delete
        :type param: string
        :param kwargs : param_key
        :returns: ticket response on ACS ('0' is returned)
        :rtype: string
        """
        return str(self.DelObject(param, **kwargs)[0]["value"])

    def DelObject(self, param, **kwargs):
        """Delete object ACS of the parameter specified i.e a remote procedure call (DeleteObject).

        :param param: parameter to be used to delete
        :type param: string
        :param kwargs : param_key
        :returns: list of dictionary with key, value, type indicating the DelObject
        :rtype: string
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid
        p, cmd, cpe_id = self._build_input_structs(
            self.cpeid, param, action="DO", **kwargs
        )

        # get raw soap response
        with self.client.settings(raw_response=True):
            response = self.client.service.DeleteObject(p, cmd, cpe_id)

        return AxirosACS._parse_soap_response(response)

    def Read_Log_Message(self, cpeid, wait=8):
        """Read ACS log messages.

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param wait: the number of tries to be done if we are not getting proper ACS response, defaults to 8
        :type wait: integer, optional
        :returns: ticket response on ACS(Log message)
        :rtype: dictionary
        """
        CommandOptionsTypeStruct_type = self.client.get_type(
            "ns0:CommandOptionsForCPELogStruct"
        )
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            "ns0:CPEIdentifierClassStruct"
        )
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.GetLogMessagesOfCPE(
                CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data
            )

        for _ in range(wait):
            time.sleep(1)
            root = ElementTree.fromstring(response.content)
            for _value in root.iter("code"):
                break
            if _value.text != "200":
                continue
            dict_value1 = {}
            for num, (key, value) in enumerate(
                zip(root.iter("ts"), root.iter("message")), start=1
            ):
                dict_value = {"time": key.text, "msg": value.text}
                dict_value1["log_msg" + str(num)] = dict_value
            return dict_value1
        return None

    def Del_Log_Message(self, cpeid, wait=8):
        """Delete ACS log messages.

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param wait: the number of tries to be done if we are not getting proper ACS response, defaults to 8
        :type wait: integer, optional
        :returns: True or None
        :rtype: Boolean
        """
        CPEIdentifierClassStruct_type = self.client.get_type(
            "ns0:CPEIdentifierClassStruct"
        )
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.DeleteLogMessagesOfCPE(
                CPEIdentifierClassStruct_data
            )

        for _ in range(wait):
            time.sleep(1)
            root = ElementTree.fromstring(response.content)
            for _value in root.iter("code"):
                break
            if _value.text == "200":
                return True
            else:
                continue
        return None

    def GPV(self, param, timeout=default_timeout):
        """Get value from CM by ACS for a single given parameter key path synchronously.

        :param param: path to the key that assigned value will be retrieved
        :return: value as a dictionary
        """
        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(
            self.cpeid, param, action="GPV", wait_time=timeout
        )

        with self.client.settings(raw_response=True):
            response = self.client.service.GetParameterValues(p, cmd, cpe_id)
        return AxirosACS._parse_soap_response(response)

    def SPV(self, param_value, timeout=default_timeout):
        """Modify the value of one or more CPE Parameters.

        It can take a single k,v pair or a list of k,v pairs.
        :param param_value: dictionary that contains the path to the key and
        the value to be set. E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :param timeout: to set the Lifetime Expiry time
        :return: status of the SPV as int (0/1)
        :raises: TR069ResponseError if the status is not (0/1)
        """
        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(
            self.cpeid, param_value, action="SPV", wait_time=timeout
        )

        with self.client.settings(raw_response=True):
            response = self.client.service.SetParameterValues(p, cmd, cpe_id)
        result = AxirosACS._parse_soap_response(response)
        status = int(result[0]["value"])
        if status not in [0, 1]:
            raise TR069ResponseError("SPV Invalid status: " + str(status))
        return status

    def GPN(self, param, next_level, timeout=default_timeout):
        """This method is used to  discover the Parameters accessible on a particular CPE

        :param param: parameter to be discovered
        :type param: string
        :next_level: displays the next level children of the object if marked true
        :type next_level: boolean
        :type timeout: to set the Lifetime Expiry time
        :return: value as a dictionary
        """

        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(
            self.cpeid, param, action="GPN", next_level=next_level, wait_time=timeout
        )

        with self.client.settings(raw_response=True):
            response = self.client.service.GetParameterNames(p, cmd, cpe_id)
        return AxirosACS._parse_soap_response(response)

    def FactoryReset(self):
        """Execute FactoryReset RPC.

        Returns true if FactoryReset request is initiated.
        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the Reeboot of the device has to be handled in the test.

        :return: returns factory reset response
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        CmdOptTypeStruct_data = self._get_cmd_data(Sync=True, Lifetime=20)
        CPEIdClassStruct_data = self._get_class_data(cpeid=self.cpeid)

        with self.client.settings(raw_response=True):
            response = self.client.service.FactoryReset(
                CommandOptions=CmdOptTypeStruct_data,
                CPEIdentifier=CPEIdClassStruct_data,
            )
        return AxirosACS._parse_soap_response(response)

    def connectivity_check(self, cpeid):
        """Check the connectivity between the ACS and the DUT by\
        requesting the DUT to perform a schedule inform.

        NOTE: The scope of this method is to verify that the ACS and DUT can
        communicate with each other!

        :param cpeid: the id to use for the ping
        :param type: string

        :return: True for a successful ScheduleInform, False otherwise
        """
        old_cpeid = self.cpeid
        self.cpeid = cpeid
        r = True
        try:
            self.ScheduleInform(DelaySeconds=1)
        except Exception as e:
            # on ANY exception assume ScheduleInform failed-> comms failed
            logger.error(e)
            logger.error(f"connectivity_check failed for {cpeid}")
            r = False
        self.cpeid = old_cpeid
        return r

    def ScheduleInform(self, CommandKey="Test", DelaySeconds=20):
        """Execute ScheduleInform RPC

        :param commandKey: the string paramenter passed to scheduleInform
        :param type: string
        :param DelaySecond: delay of seconds in integer
        :param type: integer

        :return: returns ScheduleInform response
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        param = [CommandKey, DelaySeconds]
        p, cmd, cpe_id = self._build_input_structs(self.cpeid, param, action="SI")

        with self.client.settings(raw_response=True):
            response = self.client.service.ScheduleInform(
                CommandOptions=cmd, CPEIdentifier=cpe_id, Parameters=p
            )

        return AxirosACS._parse_soap_response(response)

    def Reboot(self, CommandKey="Reboot Test"):
        """Execute Reboot.

        Returns true if Reboot request is initiated.

        :return: returns reboot RPC response
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(
            self.cpeid, CommandKey, action="REBOOT"
        )

        with self.client.settings(raw_response=True):
            response = self.client.service.Reboot(
                CommandOptions=cmd, CPEIdentifier=cpe_id, Parameters=p
            )

        return AxirosACS._parse_soap_response(response)

    def GetRPCMethods(self):
        """Execute GetRPCMethods RPC.

        :return: returns GetRPCMethods response of supported functions
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        CmdOptTypeStruct_data = self._get_cmd_data(Sync=True, Lifetime=20)
        CPEIdClassStruct_data = self._get_class_data(cpeid=self.cpeid)

        with self.client.settings(raw_response=True):
            response = self.client.service.GetRPCMethods(
                CommandOptions=CmdOptTypeStruct_data,
                CPEIdentifier=CPEIdClassStruct_data,
            )
        return AxirosACS._parse_soap_response(response)

    def Download(
        self,
        url,
        filetype="1 Firmware Upgrade Image",
        targetfilename="",
        filesize=200,
        username="",
        password="",
        commandkey="",
        delayseconds=10,
        successurl="",
        failureurl="",
    ):
        """Execute Download RPC.

        :param url: URL to download file
        :param type: string
        :param filetype: the string paramenter from following 6 values only
                         ["1 Firmware Upgrade Image", "2 Web Content",
                          "3 Vendor Configuration File", "4 Tone File",
                          "5 Ringer File", "6 Stored Firmware Image" ]
                         default="3 Vendor Configuration File"
        :param type: string
        :param targetfilename: TargetFileName to download through RPC
        :param type: string
        :param filesize: the size of file to download in bytes
        :param type: integer
        :param username: User to authenticate with file Server.  Default=""
        :param type: string
        :param password: Password to authenticate with file Server. Default=""
        :param type: string
        :param commandkey: the string paramenter passed in Download API
        :param type: string
        :param delayseconds: delay of seconds in integer
        :param type: integer
        :param successurl: URL to access in case of Download API execution succeeded
        :param type: string
        :param failureurl: URL to access in case of Download API execution Failed
        :param type: string

        :return: returns Download response
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        param = [
            commandkey,
            delayseconds,
            failureurl,
            filesize,
            filetype,
            password,
            successurl,
            targetfilename,
            url,
            username,
        ]
        p, cmd, cpe_id = self._build_input_structs(self.cpeid, param, action="DOWNLOAD")

        with self.client.settings(raw_response=True):
            response = self.client.service.Download(
                CommandOptions=cmd, CPEIdentifier=cpe_id, Parameters=p
            )
        return AxirosACS._parse_soap_response(response)

    def block_traffic(self, unblock=False):
        """block traffic to ACS server.

        :param unblock : set true to unblock traffic to dest ip
        :param type : boolean
        """
        self.dev.board.block_traffic(self.ipaddr, unblock)
        if getattr(self, "ipv6_interface", None):
            self.dev.board.block_traffic(self.ipv6_interface.ip, unblock)


if __name__ == "__main__":
    import sys
    from pprint import pprint

    """Good values to test:
    Device.DeviceInfo.ModelNumber
    Device.DeviceInfo.SoftwareVersion
    Device.DeviceInfo.Processor

    NOTE: big queries may timeout

    To use from cmdline change:
        from . import base_acs
    to:
        from boardfarm.devices import base_acs

    some cmd line samples (user/passwd from json serial no from ACS gui):

    # this must work
    python3 ./axiros_acs.py ip:port user passwd serialno GVP "'Device.DeviceInfo.ModelNumber'"

    # this must fail
    python3 ./axiros_acs.py ip:port user passwd serailno GVP "'Device.DeviceInfo.ModelNumber1'"

    # this must fail
    python3 ./axiros_acs.py ip:port user passwd serialno SVP "{'Device.DeviceInfo.ModelNumber':'mik'}"

    # this should work
    python3 ./axiros_acs.py ip:port user passwod serialno SVP "[{'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}, {'Device.WiFi.AccessPoint.2.AC.1.Alias':'mik_2'}]"

    # this must fail
    python3 ./axiros_acs.py ip:port user passwd serialno SVP "[{'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}, {'Device.WiFi.AccessPoint.2.AC.1.Alias':2}]"
    """

    if len(sys.argv) < 3:
        logger.info("Usage:")
        logger.info(
            "\tpython3 axiros_acs.py ip:port <user> <passwd> <cpeid> <action> \"'<parameter>'\"  NOTE: the quotes are importand"
        )
        logger.info(
            "\tpython3 axiros_acs.py ip:port <user> <passwd> <cpeid> <action> \"'Device.DeviceInfo.SoftwareVersion.']\""
        )
        logger.info(
            "\tpython3 axiros_acs.py ip:port <user> <passwd> <cpeid> <action> \"['Device.DeviceInfo.ModelNumber', 'Device.DeviceInfo.SoftwareVersion.']"
        )
        sys.exit(1)

    if ":" in sys.argv[1]:
        ip = sys.argv[1].split(":")[0]
        port = sys.argv[1].split(":")[1]
    else:
        ip = sys.argv[1]
        port = 80

    if len(sys.argv) > 4:
        cpe_id = sys.argv[4]
        logger.info(f"Using CPEID: {cpe_id}")
    else:
        logger.error("Error: missing cpeid")
        sys.exit(1)

    acs = AxirosACS(
        ipaddr=ip, port=port, username=sys.argv[2], password=sys.argv[3], cpeid=cpe_id
    )

    action = acs.SPV if sys.argv[5] == "SPV" else acs.GPV

    param = "Device.DeviceInfo.SoftwareVersion."
    if len(sys.argv) > 6:
        param = ast.literal_eval(sys.argv[6])

    acs.Axiros_GetListOfCPEs()
    try:
        ret = action(param)
        pprint(ret)
    except TR069FaultCode as fault:
        logger.error("==== Received TR069FaultCode exception:====")
        logger.debug(pprint(fault.faultdict))
        logger.debug("=========================================")
        raise
    except Exception as e:
        logger.error("==== Received UNEXPECTED exception:======")
        logger.debug(pprint(e))
        logger.debug("=========================================")
        raise
