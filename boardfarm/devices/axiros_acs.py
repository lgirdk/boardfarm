import os
import time

from zeep import Client
from zeep.wsse.username import UsernameToken
from zeep.transports import Transport

from requests import Session
from requests.auth import HTTPBasicAuth

from xml.etree import ElementTree

if "BFT_DEBUG" in os.environ:
    import logging.config

    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'verbose': {
                'format': '%(name)s: %(message)s'
            }
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'zeep.transports': {
                'level': 'DEBUG',
                'propagate': True,
                'handlers': ['console'],
            },
        }
    })


class AxirosACS(object):

    model = "axiros_acs_soap"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.username = self.kwargs['username']
        self.password = self.kwargs['password']
        self.ipaddr = self.kwargs['ipaddr']
        self.port = self.kwargs.get('port', None)

        if self.port is not None:
            target = self.ipaddr + ":" + self.port
        else:
            target = self.ipaddr

        self.wsdl = "http://" + target + "/live/CPEManager/DMInterfaces/soap/getWSDL"

        session = Session()
        session.auth = HTTPBasicAuth(self.username, self.password)

        self.client = Client(wsdl=self.wsdl, transport=Transport(session=session),
                             wsse=UsernameToken(self.username, self.password))

    name = "acs_server"

    def __str__(self):
        return "AxirosACS"

    def close(self):
        pass

    def get(self, serial_number, param, wait=8):
        GetParameterValuesParametersClassArray_type = self.client.get_type('ns0:GetParameterValuesParametersClassArray')
        GetParameterValuesParametersClassArray_data = GetParameterValuesParametersClassArray_type([param])

        CommandOptionsTypeStruct_type = self.client.get_type('ns0:CommandOptionsTypeStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type('ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(cpeid=serial_number)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.GetParameterValues(
                GetParameterValuesParametersClassArray_data, CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)

        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break

        if ticketid is None:
            return None
        return self.Axiros_GetTicketValue(ticketid, wait=wait)

    def getcurrent(self, serial_number, param):
        self.get(serial_number, param + '.', wait=20)
        # TODO: note: verified ticket was sent to ACS with all the results in the param namespace
        # however the get above does not pull the results so we can't check them here but that's
        # not a major issue since the API does not do that for the current implementation

    def set(self, serial_number, attr, value):
        SetParameterValuesParametersClassArray_type = self.client.get_type('ns0:SetParameterValuesParametersClassArray')
        SetParameterValuesParametersClassArray_data = SetParameterValuesParametersClassArray_type([
                                                                                                  {'key': attr, 'value': value}])

        CommandOptionsTypeStruct_type = self.client.get_type('ns0:CommandOptionsTypeStruct')
        CommandOptionsTypeStruct_data = CommandOptionsTypeStruct_type()

        CPEIdentifierClassStruct_type = self.client.get_type('ns0:CPEIdentifierClassStruct')
        CPEIdentifierClassStruct_data = CPEIdentifierClassStruct_type(cpeid=serial_number)

        # get raw soap response (parsing error with zeep)
        with self.client.settings(raw_response=True):
            response = self.client.service.SetParameterValues(
                SetParameterValuesParametersClassArray_data, CommandOptionsTypeStruct_data, CPEIdentifierClassStruct_data)

        ticketid = None
        root = ElementTree.fromstring(response.content)
        for value in root.iter('ticketid'):
            ticketid = value.text
            break

        if ticketid is None:
            return None

        return self.Axiros_GetTicketValue(ticketid)

    def Axiros_GetListOfCPEs(self):
        CPESearchOptionsClassStruct_type = self.client.get_type('ns0:CPESearchOptionsClassStruct')
        CPESearchOptionsClassStruct_data = CPESearchOptionsClassStruct_type()

        CommandOptionsForCPESearchStruct_type = self.client.get_type('ns0:CommandOptionsForCPESearchStruct')
        CommandOptionsForCPESearchStruct_data = CommandOptionsForCPESearchStruct_type()

        response = self.client.service.GetListOfCPEs(
            CPESearchOptionsClassStruct_data, CommandOptionsForCPESearchStruct_data)
        if response['code'] != 200:
            return None

        return response

    def Axiros_GetTicketResponse(self, ticketid):
        response = self.client.service.get_generic_sb_result(ticketid)

        if response['code'] != 200:
            return None

        return response['code']

    def Axiros_GetTicketValue(self, ticketid, wait=8):
        for i in range(wait):
            time.sleep(1)
            with self.client.settings(raw_response=True):
                ticket_resp = self.client.service.get_generic_sb_result(ticketid)

            root = ElementTree.fromstring(ticket_resp.content)
            for value in root.iter('code'):
                break
            if (value.text != '200'):
                continue
            for value in root.iter('value'):
                return value.text
        return None


if __name__ == '__main__':
    import sys

    if ':' in sys.argv[1]:
        ip = sys.argv[1].split(':')[0]
        port = sys.argv[1].split(':')[1]
    else:
        ip = sys.argv[1]
        port = 80

    acs = AxirosACS(ipaddr=ip, port=port, username=sys.argv[2], password=sys.argv[3])

    acs.Axiros_GetListOfCPEs()

    ret = acs.get('DEAP805811D5', 'Device.DeviceInfo.SoftwareVersion')
    print(ret)

    ret = acs.get('DEAP805811D5', 'Device.WiFi.SSID.1.SSID')
    print(ret)
