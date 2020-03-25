import ipaddress
import time
from xml.etree import ElementTree

from boardfarm.exceptions import ACSFaultCode
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.transports import Transport
from zeep.wsse.username import UsernameToken

from . import base_acs


class AxirosACS(base_acs.BaseACS):
    """ACS connection class used to perform TR069 operations on stations/board
    """
    model = "axiros_acs_soap"
    name = "acs_server"

    def __init__(self, *args, **kwargs):
        """This method intializes the varible that are used in establishing connection to the ACS.
           The method intializes an HTTP SOAP client which will authenticate with the ACS server.

        :param *args: the arguments to be used if any
        :type *args: tuple
        :param **kwargs: extra args to be used if any (mainly contains username, password, ipadress and port)
        :type **kwargs: dict
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

        self.client = Client(wsdl=self.wsdl,
                             transport=Transport(session=session),
                             wsse=UsernameToken(self.username, self.password))

        #to spawn pexpect on cli
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

    def __str__(self):
        """The method is used to format the string representation of self object (instance).

        :returns: :class:`Response <Response>` string representation of self object.
        :rtype: string
        """
        return "AxirosACS"

    def close(self):
        """Method to be implemented to close ACS connection
        """
        pass

    def get_ticketId(self, cpeid, param):
        """ACS server maintains a ticket ID for all TR069 RPC calls.

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

    def get(self, cpeid, param, wait=8):
        """This method is used to perform a remote procedure call (GetParameterValue)

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
        ticketid = self.get_ticketId(cpeid, param)
        if ticketid is None:
            return None
        return self.Axiros_GetTicketValue(ticketid, wait=wait)

    def getcurrent(self, cpeid, param, wait=8):
        """This method is used to get the key, value of the response for the given parameter from board.
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
        ticketid = self.get_ticketId(cpeid, param)
        for i in range(wait):
            time.sleep(1)
            with self.client.settings(raw_response=True):
                ticket_resp = self.client.service.get_generic_sb_result(
                    ticketid)
            root = ElementTree.fromstring(ticket_resp.content)
            for value in root.iter('code'):
                break
            if (value.text != '200'):
                continue
            dict_key_value = {}
            for key, value in zip(root.iter('key'), root.iter('value')):
                dict_key_value[key.text] = value.text
            return dict_key_value

    def set(self, cpeid, attr, value):
        """This method is used to set a parameter in board via TR069 RPC call (SetParameterValue).

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
        SetParameterValuesParametersClassArray_type = self.client.get_type(
            'ns0:SetParameterValuesParametersClassArray')
        SetParameterValuesParametersClassArray_data = SetParameterValuesParametersClassArray_type(
            [{
                'key': attr,
                'value': value
            }])

        CommandOptionsTypeStruct_type = self.client.get_type(
            'ns0:CommandOptionsTypeStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            'ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(
            cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.SetParameterValues(
                SetParameterValuesParametersClassArray_data,
                CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)

        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break

        if ticketid is None:
            return None

        return self.Axiros_GetTicketValue(ticketid)

    def Axiros_GetListOfCPEs(self):
        """This method is used to get the list of all devices registered on the ACS server.

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
        """This method is used to delete a CPE on the ACS server.

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
        """This is helper method used to get the ticket response on ACS.

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
        """This is helper method used to get the text of ticket response on ACS.

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
        for i in range(wait):
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

    def rpc_GetParameterAttributes(self, cpeid, param):
        """This method is used to get parameter attribute on ACS of the parameter specified i.e a remote procedure call (GetParameterAttribute).
        Example usage : acs_server.rpc_GetParameterAttributes('DEAP815610DA', 'Device.WiFi.SSID.1.SSID')

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used in get
        :type param: string
        :raises: NA
        :returns: dictionary with keys Name, Notification (0/1), AccessList indicating the GPA
        :rtype: dict
        """
        GetParameterAttrParametersClassArray_type = self.client.get_type(
            'ns0:GetParameterAttributesParametersClassArray')
        GetParameterAttrParametersClassArray_data = GetParameterAttrParametersClassArray_type(
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
            response = self.client.service.GetParameterAttributes(
                GetParameterAttrParametersClassArray_data,
                CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)
        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break

        if ticketid is None:
            return None

        for i in range(8):
            time.sleep(1)
            with self.client.settings(raw_response=True):
                ticket_resp = self.client.service.get_generic_sb_result(
                    ticketid)

            root = ElementTree.fromstring(ticket_resp.content)
            for value in root.iter('code'):
                break
            if (value.text != '200'):
                continue
            dict_value = {'Name': param}
            for iter_value in ['Notification', 'item']:
                for value in root.iter(iter_value):
                    dict_value[iter_value] = value.text
            dict_value['AccessList'] = dict_value.pop('item')
            return dict_value

        assert False, "rpc_GetParameterAttributes failed to lookup %s" % param

    def rpc_SetParameterAttributes(self, cpeid, attr, value):
        """This method is used to set parameter attribute on ACS of the parameter specified i.e a remote procedure call (SetParameterAttribute).

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
        SetParameterAttrParametersClassArray_type = self.client.get_type(
            'ns0:SetParameterAttributesParametersClassArray')
        SetParameterAttrParametersClassArray_data = SetParameterAttrParametersClassArray_type(
            [{
                'Name': attr,
                'Notification': value,
                'AccessListChange': '0',
                'AccessList': {
                    'item': 'Subscriber'
                },
                'NotificationChange': '1'
            }])

        CommandOptionsTypeStruct_type = self.client.get_type(
            'ns0:CommandOptionsTypeStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            'ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(
            cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.SetParameterAttributes(
                SetParameterAttrParametersClassArray_data,
                CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)

        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break

        if ticketid is None:
            return None

        return self.Axiros_GetTicketValue(ticketid)

    def rpc_AddObject(self, cpeid, param, wait=8):
        """This method is used to add object ACS of the parameter specified i.e a remote procedure call (AddObject).

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
        AddObjectClassArray_type = self.client.get_type(
            'ns0:AddDelObjectArgumentsStruct')
        AddObjectClassArray_data = AddObjectClassArray_type(param, '')

        CommandOptionsTypeStruct_type = self.client.get_type(
            'ns0:CommandOptionsTypeStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            'ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(
            cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.AddObject(AddObjectClassArray_data, \
                                      CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)
        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break

        if ticketid is None:
            return None

        for i in range(wait):
            time.sleep(1)
            with self.client.settings(raw_response=True):
                ticket_resp = self.client.service.get_generic_sb_result(
                    ticketid)

            root = ElementTree.fromstring(ticket_resp.content)
            for value in root.iter('code'):
                break
            if (value.text != '200'):
                continue
            dict_value = {}
            for key, value in zip(root.iter('key'), root.iter('value')):
                dict_value[key.text] = value.text
            return dict_value

        assert False, "rpc_AddObject failed to lookup %s" % param

    def rpc_DelObject(self, cpeid, param):
        """This method is used to delete object ACS of the parameter specified i.e a remote procedure call (DeleteObject).

        :param cpeid: the serial number of the modem through which ACS communication happens.
        :type cpeid: string
        :param param: parameter to be used to delete
        :type param: string
        :returns: ticket response on ACS ('0' is returned)
        :rtype: string
        """
        DelObjectClassArray_type = self.client.get_type(
            'ns0:AddDelObjectArgumentsStruct')
        DelObjectClassArray_data = DelObjectClassArray_type(param, '')

        CommandOptionsTypeStruct_type = self.client.get_type(
            'ns0:CommandOptionsTypeStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type(
            'ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(
            cpeid=cpeid)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.DeleteObject(DelObjectClassArray_data, \
                                             CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)

        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break

        if ticketid is None:
            return None

        return self.Axiros_GetTicketValue(ticketid)

    def Read_Log_Message(self, cpeid, wait=8):
        """This method is used to read ACS log messages

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

        for i in range(wait):
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
        """This method is used to delete ACS log messages

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

        for i in range(wait):
            time.sleep(1)
            root = ElementTree.fromstring(response.content)
            for value in root.iter('code'):
                break
            if (value.text == '200'):
                return True
            else:
                continue
        return None


if __name__ == '__main__':
    import sys

    if ':' in sys.argv[1]:
        ip = sys.argv[1].split(':')[0]
        port = sys.argv[1].split(':')[1]
    else:
        ip = sys.argv[1]
        port = 80

    acs = AxirosACS(ipaddr=ip,
                    port=port,
                    username=sys.argv[2],
                    password=sys.argv[3])

    acs.Axiros_GetListOfCPEs()

    ret = acs.get('DEAP805811D5', 'Device.DeviceInfo.SoftwareVersion')
    print(ret)

    ret = acs.get('DEAP805811D5', 'Device.WiFi.SSID.1.SSID')
    print(ret)
