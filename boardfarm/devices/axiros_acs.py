import ast
import ipaddress
import os
import re
import time
import warnings
import xml.dom.minidom
from datetime import datetime
from xml.etree import ElementTree

import pexpect
import xmltodict
from boardfarm.exceptions import (ACSFaultCode, CodeError, TR069FaultCode,
                                  TR069ResponseError)
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from boardfarm.lib.network_testing import (kill_process, tcpdump_capture,
                                           tshark_read)
from debtcollector import moves
from nested_lookup import nested_lookup
from requests import HTTPError, Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.cache import InMemoryCache
from zeep.transports import Transport
from zeep.wsse.username import UsernameToken

from . import base_acs

warnings.simplefilter('always')


class AxirosACS(base_acs.BaseACS):
    """ACS connection class used to perform TR069 operations on stations/board."""
    model = "axiros_acs_soap"
    name = "acs_server"
    # should the following be dynamic?
    namespaces = {'http://www.w3.org/2001/XMLSchema-instance': None}
    CPE_wait_time = 60 * 1  # too long?
    Count_retry_on_error = 3  # to be audited

    def __init__(self, *args, **kwargs):
        """Intialize the varible that are used in establishing connection to the ACS and\
           Intialize an HTTP SOAP client which will authenticate with the ACS server.

        :param ``*args``: the arguments to be used if any
        :type ``*args``: tuple
        :param ``**kwargs``: extra args to be used if any (mainly contains username, password, ipadress and port)
        :type ``**kwargs``: dict
        """
        self.args = args
        self.kwargs = kwargs
        self.username = self.kwargs['username']
        self.password = self.kwargs['password']
        self.ipaddr = self.kwargs['ipaddr']
        self.port = self.kwargs.get('port', None)
        self.cli_port = self.kwargs.pop('cli_port', '22')
        self.cli_username = self.kwargs.pop('cli_username', None)
        self.cli_password = self.kwargs.pop('cli_password', None)
        self.color = self.kwargs.pop('color', None)
        self.options = self.kwargs.pop('options', None)
        AxirosACS.CPE_wait_time = self.kwargs.pop('wait_time',
                                                  AxirosACS.CPE_wait_time)

        if self.options:
            options = [x.strip() for x in self.options.split(',')]
            for opt in options:
                if opt.startswith('wan-static-ipv6:'):
                    ipv6_address = opt.replace('wan-static-ipv6:', '').strip()
                    if "/" not in opt:
                        ipv6_address += "/64"
                    self.ipv6_interface = ipaddress.IPv6Interface(ipv6_address)
                    self.gwv6 = self.ipv6_interface.ip

        if self.port is not None:
            target = self.ipaddr + ":" + self.port
        else:
            target = self.ipaddr

        self.wsdl = "http://" + target + "/live/CPEManager/DMInterfaces/soap/getWSDL"

        session = Session()
        session.auth = HTTPBasicAuth(self.username, self.password)

        self.client = Client(
            wsdl=self.wsdl,
            transport=Transport(session=session,
                                cache=InMemoryCache(timeout=3600 * 3)),
            wsse=UsernameToken(self.username, self.password),
        )

        # to spawn pexpect on cli
        if all([self.ipaddr, self.cli_username, self.cli_password]):
            bft_pexpect_helper.spawn.__init__(
                self,
                command="ssh",
                args=[
                    '%s@%s' % (self.cli_username, self.ipaddr), '-p',
                    self.cli_port, '-o', 'StrictHostKeyChecking=no', '-o',
                    'UserKnownHostsFile=/dev/null', '-o',
                    'ServerAliveInterval=60', '-o', 'ServerAliveCountMax=5'
                ])
            self.check_connection(self.cli_username, self.name,
                                  self.cli_password)
            self.print_connected_console_msg(self.ipaddr, self.cli_port,
                                             self.color, self.name)
        # this should be populater ONLY when using __main__
        self.cpeid = self.kwargs.pop('cpeid', None)

    def sudo_sendline(self, cmd):
        # overwriting linux behaviour
        # this is under assumption that acs is having root credentials.
        self.sendline(cmd)

    def tcp_dump(func):
        """ Decorator to capture tcpdump in error cases
        """
        def wrapper(self, *args, **kwargs):
            try:
                capture_file = "acs_debug" + time.strftime(
                    "%Y%m%d-%H%M%S") + ".pcap"
                tcpdump_capture(self, "any", capture_file=capture_file)
                out = func(self, *args, **kwargs)
                kill_process(self, process="tcpdump")
                return out
            except Exception as e:
                kill_process(self, process="tcpdump")
                tshark_read(self, capture_file, filter_str="-Y http")
                raise (e)
            finally:
                self.sendline("rm %s" % capture_file)

        return wrapper

    def __str__(self):
        """Format the string representation of self object (instance).

        :returns: :class:`Response <Response>` string representation of self object.
        :rtype: string
        """
        return "AxirosACS"

    # TO DO: maybe this could be moved to a lib
    def _data_conversion(d):
        """Conversion type/data helper."""
        def to_int(v):
            return int(v)

        def to_bool(v):
            if v == '1':
                return 'true'
            elif v == '0':
                return 'false'
            return v

        def to_dateTime(v):
            if re.search(r'^1\s', v):
                v = v.zfill(len(v) + 3)
            v = datetime.strptime(
                v, '%Y %m %d %H %M %S.0').strftime('%Y-%m-%dT%H:%M:%S')
            return v

        conv_table = {
            'xsd3:string': {
                'string': None
            },
            'xsd3:integer': {
                'integer': to_int
            },
            'xsd3:boolean': {
                'boolean': to_bool
            },
            'xsd3:ur-type[6]': {
                'dateTime': to_dateTime
            }
        }
        convdict = conv_table.get(d['type'])
        if convdict:
            d['type'] = next(iter(convdict))
            if d['value'] != '' and convdict[d['type']]:
                v = convdict[d['type']](d['value'])
                d['value'] = v
        return d

    @staticmethod
    def _parse_xml_response(data_values):
        data_list = []
        if type(data_values) is list:
            pass
        else:
            data_values = [data_values]
        for data in data_values:
            if 'AccessList' in data['value']:
                data_list.append({
                    'Name':
                    data['key']['text'],
                    'AccessList':
                    data['value']['AccessList']['item']['text'],
                    'Notification':
                    data['value']['Notification']['text']
                })
            else:
                v = data['value'].get('text', '')
                if v == '':
                    if 'item' in data['value']:
                        v = " ".join(
                            [val.get('text') for val in data['value']['item']])
                val_type = data['value']['type']
                if val_type == 'SOAP-ENC:Array':
                    val_type = data['value'][
                        'http://schemas.xmlsoap.org/soap/encoding/:arrayType']
                data_list.append(
                    AxirosACS._data_conversion({
                        'key': data['key']['text'],
                        'type': val_type,
                        'value': v
                    }))

        return data_list

    @staticmethod
    def _get_xml_key(resp, k='text'):
        result = nested_lookup(
            'Result',
            xmltodict.parse(resp.content,
                            attr_prefix='',
                            cdata_key=k,
                            process_namespaces=True,
                            namespaces=AxirosACS.namespaces))
        return result

    @staticmethod
    def _parse_soap_response(response):
        """Parse the ACS response and return a\
        list of dictionary with {key,type,value} pair."""
        if 'BFT_DEBUG' in os.environ:
            msg = xml.dom.minidom.parseString(response.text)
            print(msg.toprettyxml(indent=' ', newl=""))

        result = AxirosACS._get_xml_key(response)
        if len(result) > 1:
            raise KeyError("More than 1 Result in reply not implemented yet")
        result = result[0]
        httpcode = result['code']['text']
        msg = result['message']['text']
        http_error_message = "HTTP Error code:" + httpcode + " " + msg
        if httpcode != '200':
            # with 507 (timeout/expired) there seem to be NO faultcode message
            if httpcode == '500':
                if 'faultcode' not in result['message']['text']:
                    raise HTTPError(http_error_message)
            else:
                raise HTTPError(http_error_message)

        # is this needed (might be overkill)?
        if not all([
                result.get('details'),
                result.get('message'),
                result.get('ticketid')
        ]):
            e = TR069ResponseError(
                'ACS malformed response (issues with either '
                'details/message/ticketid).')
            e.result = result  # for inspection later
            raise e
        fault = 'faultcode' in msg
        if fault:
            # could there be more than 1 fault in a response?
            e = TR069FaultCode(msg)
            e.faultdict = \
                ast.literal_eval(msg[msg.index('{'):])
            raise e
        # 'item' is not present in FactoryReset RPC response
        if 'item' in result['details']:
            return AxirosACS._parse_xml_response(result['details']['item'])
        elif 'ns1:KeyValueStruct[0]' in result['details'][
                'http://schemas.xmlsoap.org/soap/encoding/:arrayType']:
            return []

    def _get_cmd_data(self, *args, **kwagrs):
        """Return CmdOptTypeStruct_data. It is a helper method."""
        c_opt_type = 'ns0:CommandOptionsTypeStruct'
        CmdOptTypeStruct_type = self.client.get_type(c_opt_type)
        CmdOptTypeStruct_data = CmdOptTypeStruct_type(*args, **kwagrs)
        return CmdOptTypeStruct_data

    def _get_class_data(self, *args, **kwagrs):
        """Return CPEIdClassStruct_data. It is a helper method."""
        cpe__id_type = 'ns0:CPEIdentifierClassStruct'
        CPEIdClassStruct_type = self.client.get_type(cpe__id_type)
        CPEIdClassStruct_data = CPEIdClassStruct_type(*args, **kwagrs)
        return CPEIdClassStruct_data

    def _get_pars_val_data(self, p_arr_type, *args, **kwargs):
        """Return ParValsParsClassArray_data.It is a helper method."""
        ParValsClassArray_type = self.client.get_type(p_arr_type)
        ParValsParsClassArray_data = ParValsClassArray_type(*args, **kwargs)
        return ParValsParsClassArray_data

    def _build_input_structs(self,
                             cpeid,
                             param,
                             action,
                             next_level=None,
                             **kwargs):
        """Helper function to create the get structs used in the get/set param values

        NOTE: The command option is set as Syncronous
        :param cpeid: the serial number of the modem through which ACS communication
        happens.
        :type cpeid: string
        :param param: parameter to used
        :type param: string or list of strings for get, dict or list of dict for set
        :param action: one of GPV/SPV/GPN/AO/DO/SI/REBOOT
        :type action: string
        :param next_level: defaults to null takes True/False
        :type next_level: boolean
        :raises: NA
        :returns: param_data, cmd_data, cpeid_data
        """
        if action == 'SPV':
            if type(param) is not list:
                param = [param]
            l = []
            # this is a list of single k,v pairs
            for d in param:
                k = next(iter(d))
                l.append({'key': k, 'value': d[k]})
            p_arr_type = 'ns0:SetParameterValuesParametersClassArray'
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, l)

        elif action == 'GPV':
            if type(param) is not list:
                param = [param]
            p_arr_type = 'ns0:GetParameterValuesParametersClassArray'
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, param)

        elif action == 'SPA':
            if type(param) is not list:
                param = [param]
            l = []
            for d in param:
                k = next(iter(d))
                l.append({
                    'Name':
                    k,
                    'Notification':
                    d[k],
                    'AccessListChange':
                    kwargs.get("access_param", '0'),
                    'AccessList': {
                        'item': 'Subscriber'
                    },
                    'NotificationChange':
                    kwargs.get("notification_param", '1')
                })
            p_arr_type = 'ns0:SetParameterAttributesParametersClassArray'
            ParValsParsClassArray_data = self._get_pars_val_data(p_arr_type, l)

        elif action == 'GPN':

            p_arr_type = 'ns0:GetParameterNamesArgumentsStruct'
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, NextLevel=next_level, ParameterPath=param)

        elif action == 'GPA':
            if type(param) is not list:
                param = [param]
            p_arr_type = 'ns0:GetParameterAttributesParametersClassArray'
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, param)

        elif action == "SI":
            if type(param) is not list:
                param = [param]
            p_arr_type = 'ns0:ScheduleInformArgumentsStruct'
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, *param)

        elif action in ['AO', 'DO']:
            p_arr_type = 'ns0:AddDelObjectArgumentsStruct'
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, param, '')

        elif action == "REBOOT":
            p_arr_type = 'xsd:string'
            ParValsParsClassArray_data = self._get_pars_val_data(
                p_arr_type, param)

        else:
            raise CodeError('Invalid action: ' + action)

        CmdOptTypeStruct_data = self._get_cmd_data(
            Sync=True, Lifetime=AxirosACS.CPE_wait_time)

        CPEIdClassStruct_data = self._get_class_data(cpeid=cpeid)

        return ParValsParsClassArray_data,\
            CmdOptTypeStruct_data,\
            CPEIdClassStruct_data

    def close(self):
        """Implement to close ACS connection. TODO."""
        pass

    def get_ticketId(self, cpeid, param):
        """ACS server maintain a ticket ID for all TR069 RPC calls.

        This method will contruct a TR069 GPV query, execute it and
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
            'ns0:GetParameterValuesParametersClassArray')
        GetParameterValuesParametersClassArray_data = GetParameterValuesParametersClassArray_type(
            [param])

        CommandOptionsTypeStruct_type = self.client.get_type(
            'ns0:CommandOptionsTypeStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            'ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(
            cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.GetParameterValues(
                GetParameterValuesParametersClassArray_data,
                CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)

        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break
        return ticketid

    @moves.moved_method('GPV')
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
        :returns: first value of ACS reponse for the parameter.
        :rtype: string
        """
        try:
            return self.GPV(param)[0]['value']
        except Exception as e:
            print(e)
            return None

    @moves.moved_method('GPV')
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
            dict_key_value = {item['key']: item['value'] for item in out}
            return dict_key_value
        except Exception as e:
            print(e)
            return {}

    @moves.moved_method('SPV')
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
            param = {}
            param[attr] = value
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
            'ns0:CPESearchOptionsClassStruct')
        CPESearchOptionsClassStruct_data = CPESearchOptionsClassStruct_type()

        CommandOptionsForCPESearchStruct_type = self.client.get_type(
            'ns0:CommandOptionsForCPESearchStruct')
        CommandOptionsForCPESearchStruct_data = CommandOptionsForCPESearchStruct_type(
        )

        response = self.client.service.GetListOfCPEs(
            CPESearchOptionsClassStruct_data,
            CommandOptionsForCPESearchStruct_data)
        if response['code'] != 200:
            return None

        return response

    def Axiros_DeleteCPEs(self, cpeid):
        """Delete a CPE on the ACS server.

        :raises: NA
        :returns: True if successful
        :rtype: True/False
        """
        CPESearchOptionsClassStruct_type = self.client.get_type(
            'ns0:CPESearchOptionsClassStruct')
        CPESearchOptionsClassStruct_data = CPESearchOptionsClassStruct_type(
            cpeid=cpeid)

        CommandOptionsForCPESearchStruct_type = self.client.get_type(
            'ns0:CommandOptionsForCPESearchStruct')
        CommandOptionsForCPESearchStruct_data = CommandOptionsForCPESearchStruct_type(
        )

        response = self.client.service.DeleteCPEs(
            CPESearchOptionsClassStruct_data,
            CommandOptionsForCPESearchStruct_data)
        print(response)
        if response['code'] != 200:
            return False

        return True

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

        if response['code'] != 200:
            return None

        return response['code']

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
                ticket_resp = self.client.service.get_generic_sb_result(
                    ticketid)

            root = ElementTree.fromstring(ticket_resp.content)
            for value in root.iter('code'):
                break
            if (value.text != '200'):
                for message in root.iter('message'):
                    if message.text:
                        if 'faultcode' in message.text:
                            raise ACSFaultCode(message.text)
                    break
                continue
            for value in root.iter('value'):
                if all([objtype, value.text]):
                    for key, object_type in value.attrib.items():
                        if 'type' in key:
                            return object_type.split(":")[1]
                else:
                    return value.text
        return None

    @tcp_dump
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

        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param,
                                                   action='GPA')

        with self.client.settings(raw_response=True):
            response = self.client.service.GetParameterAttributes(
                p, cmd, cpe_id)
        return AxirosACS._parse_soap_response(response)

    @moves.moved_method('GPA')
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
            print(e)
            return {}

    @moves.moved_method('SPA')
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
            param = {}
            param[attr] = value
            return self.SPA(param)
        except Exception as e:
            print(e)
            return None

    @tcp_dump
    def SPA(self, param, **kwargs):
        """Get parameter attribute on ACS of the parameter specified i.e a remote procedure call (GetParameterAttribute).

        Example usage : acs_server.SPA({'Device.WiFi.SSID.1.SSID':'1'}),could be parameter list of dicts/dict containing param name and notifications
        :param param: parameter to be used in set
        :type param: string
        :param kwargs : access_param,notification_param
        :returns: SPA response
        :rtype: dict
        """

        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param,
                                                   action='SPA',
                                                   **kwargs)

        with self.client.settings(raw_response=True):
            response = self.client.service.SetParameterAttributes(
                p, cmd, cpe_id)
        return AxirosACS._parse_soap_response(response)

    @moves.moved_method('AddObject')
    def rpc_AddObject(self, cpeid, param, wait=8):
        """Add object ACS of the parameter specified i.e a remote procedure call (AddObject).

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used to add
        :type param: string
        :param wait: the number of tries to be done if we are not getting proper ACS response, defaults to 8
        :type wait: integer, optional
        :raises assertion: rpc_AddObject failed to lookup for the param
        :returns: ticket response on ACS
        :rtype: dictionary
        """
        return {i['key']: i['value'] for i in self.AddObject(param)}

    def AddObject(self, param):
        """Add object ACS of the parameter specified i.e a remote procedure call (AddObject).

        :param param: parameter to be used to add
        :type param: string
        :raises assertion: On failure
        :returns: list of dictionary with key, value, type indicating the AddObject
        :rtype: dictionary
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid
        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param,
                                                   action='AO')

        # get raw soap response
        with self.client.settings(raw_response=True):
            response = self.client.service.AddObject(p, cmd, cpe_id)

        return AxirosACS._parse_soap_response(response)

    @moves.moved_method('DelObject')
    def rpc_DelObject(self, cpeid, param):
        """Delete object ACS of the parameter specified i.e a remote procedure call (DeleteObject).

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used to delete
        :type param: string
        :returns: ticket response on ACS ('0' is returned)
        :rtype: string
        """
        return str(self.DelObject(param)[0]['value'])

    def DelObject(self, param):
        """Delete object ACS of the parameter specified i.e a remote procedure call (DeleteObject).

        :param param: parameter to be used to delete
        :type param: string
        :returns: list of dictionary with key, value, type indicating the DelObject
        :rtype: string
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid
        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param,
                                                   action='DO')

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
            'ns0:CommandOptionsForCPELogStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            'ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(
            cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.GetLogMessagesOfCPE(
                CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)

        for _ in range(wait):
            time.sleep(1)
            root = ElementTree.fromstring(response.content)
            for value in root.iter('code'):
                break
            if (value.text != '200'):
                continue
            dict_value1 = {}
            num = 1
            for key, value in zip(root.iter('ts'), root.iter('message')):
                dict_value = {}
                dict_value['time'] = key.text
                dict_value['msg'] = value.text
                dict_value1['log_msg' + str(num)] = dict_value
                num += 1
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
            'ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(
            cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.DeleteLogMessagesOfCPE(
                CPEIdentifierClassStruct_data)

        for _ in range(wait):
            time.sleep(1)
            root = ElementTree.fromstring(response.content)
            for value in root.iter('code'):
                break
            if (value.text == '200'):
                return True
            else:
                continue
        return None

    @tcp_dump
    def GPV(self, param):
        """Get value from CM by ACS for a single given parameter key path synchronously.

        :param param: path to the key that assigned value will be retrieved
        :return: value as a dictionary
        """
        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param,
                                                   action='GPV')

        val = 0
        while val <= 1:
            try:
                with self.client.settings(raw_response=True):
                    response = self.client.service.GetParameterValues(
                        p, cmd, cpe_id)
                return AxirosACS._parse_soap_response(response)
            except HTTPError as e:
                if "507" not in str(e):
                    raise (e)
                else:
                    # adding 10 sec timeout
                    warnings.warn(
                        "Ten seconds of timeout is added to compensate DOS attack."
                    )
                    self.expect(pexpect.TIMEOUT, timeout=10)
                    if val == 1:
                        raise (e)
                    val += 1

    @tcp_dump
    def SPV(self, param_value):
        """Modify the value of one or more CPE Parameters.

        It can take a single k,v pair or a list of k,v pairs.
        :param param_value: dictionary that contains the path to the key and
        the value to be set. E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :return: status of the SPV as int (0/1)
        :raises: TR069ResponseError if the status is not (0/1)
        """
        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param_value,
                                                   action='SPV')

        val = 0
        while val <= 1:
            try:
                with self.client.settings(raw_response=True):
                    response = self.client.service.SetParameterValues(
                        p, cmd, cpe_id)
                result = AxirosACS._parse_soap_response(response)
                break
            except HTTPError as e:
                if "507" not in str(e):
                    raise (e)
                else:
                    # adding 10 sec timeout
                    warnings.warn(
                        "Ten seconds of timeout is added to compensate DOS attack."
                    )
                    self.expect(pexpect.TIMEOUT, timeout=10)
                    if val == 1:
                        raise (e)
                    val += 1
        status = int(result[0]['value'])
        if status not in [0, 1]:
            raise TR069ResponseError("SPV Invalid status: " + str(status))
        return status

    @tcp_dump
    def GPN(self, param, next_level):
        """This method is used to  discover the Parameters accessible on a particular CPE

        :param param: parameter to be discovered
        :type param: string
        :next_level: displays the next level children of the object if marked true
        :type next_level: boolean
        :return: value as a dictionary
        """

        # TO DO: ideally this should come off the environment helper
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param,
                                                   action='GPN',
                                                   next_level=next_level)

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
                CPEIdentifier=CPEIdClassStruct_data)
        return AxirosACS._parse_soap_response(response)

    def connectivity_check(self, cpeid):
        """Check the connectivity between the ACS and the DUT by\
        requesting the DUT to perform a schedule inform.

        NOTE: The scope of this method is to verify that the ACS and DUT can
        communicate with eachother!

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
            print(e)
            print(f"connectivity_check failed for {cpeid}")
            r = False
        self.cpeid = old_cpeid
        return r

    def ScheduleInform(self, CommandKey='Test', DelaySeconds=20):
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
        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   param,
                                                   action='SI')

        with self.client.settings(raw_response=True):
            response = self.client.service.ScheduleInform(CommandOptions=cmd,
                                                          CPEIdentifier=cpe_id,
                                                          Parameters=p)

        return AxirosACS._parse_soap_response(response)

    def Reboot(self, CommandKey="Reboot Test"):
        """Execute Reboot.

        Returns true if Reboot request is initiated.

        :return: returns reboot RPC response
        """
        if self.cpeid is None:
            self.cpeid = self.dev.board._cpeid

        p, cmd, cpe_id = self._build_input_structs(self.cpeid,
                                                   CommandKey,
                                                   action='REBOOT')

        with self.client.settings(raw_response=True):
            response = self.client.service.Reboot(CommandOptions=cmd,
                                                  CPEIdentifier=cpe_id,
                                                  Parameters=p)

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
                CPEIdentifier=CPEIdClassStruct_data)
        return AxirosACS._parse_soap_response(response)


if __name__ == '__main__':
    from pprint import pprint
    import sys
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
        print("Usage:")
        print(
            '\tpython3 axiros_acs.py ip:port <user> <passwd> <cpeid> <action> "\'<parameter>\'"  NOTE: the quotes are importand'
        )
        print(
            '\tpython3 axiros_acs.py ip:port <user> <passwd> <cpeid> <action> "\'Device.DeviceInfo.SoftwareVersion.\']"'
        )
        print(
            '\tpython3 axiros_acs.py ip:port <user> <passwd> <cpeid> <action> "[\'Device.DeviceInfo.ModelNumber\', \'Device.DeviceInfo.SoftwareVersion.\']'
        )
        sys.exit(1)

    if ':' in sys.argv[1]:
        ip = sys.argv[1].split(':')[0]
        port = sys.argv[1].split(':')[1]
    else:
        ip = sys.argv[1]
        port = 80

    if len(sys.argv) > 4:
        cpe_id = sys.argv[4]
        print("Using CPEID: {}".format(cpe_id))
    else:
        print('Error: missing cpeid')
        sys.exit(1)

    acs = AxirosACS(ipaddr=ip,
                    port=port,
                    username=sys.argv[2],
                    password=sys.argv[3],
                    cpeid=cpe_id)

    action = acs.SPV if sys.argv[5] == 'SPV' else acs.GPV

    param = 'Device.DeviceInfo.SoftwareVersion.'
    if len(sys.argv) > 6:
        param = ast.literal_eval(sys.argv[6])

    acs.Axiros_GetListOfCPEs()
    try:
        ret = action(param)
        pprint(ret)
    except TR069FaultCode as fault:
        print('==== Received TR069FaultCode exception:====')
        pprint(fault.faultdict)
        print('=========================================')
        raise
    except Exception as e:
        print('==== Received UNEXPECTED exception:======')
        pprint(e)
        print('=========================================')
        raise
