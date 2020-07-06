from boardfarm.devices import base


class BaseACS(base.BaseDevice):
    """Base ACS class to define methods to perfrom common ACS APIs."""

    model = "base_acs"
    name = "acs_server"
    namespaces = {"http://www.w3.org/2001/XMLSchema-instance": None}
    CPE_wait_time = 60 * 1
    Count_retry_on_error = 3

    def __init__(self, *args, **kwargs):
        """Intialize the varible that are used in establishing connection to the ACS and\
           Intialize an HTTP SOAP client which will authenticate with the ACS server.

        :param ``*args``: the arguments to be used if any
        :type ``*args``: tuple
        :param ``**kwargs``: extra args to be used if any
        (mainly contains username, password, ipadress and port)
        :type ``**kwargs``: dict
        """

        # listing down the basic expected args
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

        # logic for target ip:port
        # depends on construct used
        self.target = None
        self.wsdl = None
        self.cpeid = self.kwargs.pop("cpeid", None)

        # need to implement logic to connect to ACS
        self.connect()

    def connect(self):
        """Based on kwargs perform a establish a connection with ACS server"""
        raise Exception("Not implemented!")

    def __str__(self):
        """Format the string representation of self object (instance).

        :returns: :class:`Response <Response>` string representation of self object.
        :rtype: string
        """
        return "BaseACS"

    @staticmethod
    def _data_conversion(d):
        """Conversion type/data helper.

        Use this API to handle data conversion specific to an ACS model.

        :param d: data returned from executing an RPC on ACS
        :type d: str / list / dict
        """
        raise Exception("Not implemented!")

    @staticmethod
    def _parse_xml_response(data_values):
        """Parse XML response

        Use this API to fetch data made via HTTP calls in ACS.

        :param data_values: data returned from executing an RPC on ACS
        :type data_values: str / list / dict
        """
        raise Exception("Not implemented!")

    @staticmethod
    def _get_xml_key(resp, k="text"):
        """Parse XML response

        Use this API to fetch data made via HTTP calls in ACS.

        :param resp: xml tree response via an HTTP call
        :type data_values: xml.etree.ElementTree
        :param k: key to be searched in parsed xml tree, defaults to 'text'
        :type k: string
        :return: values for particular element
        :rtype: dict
        """
        raise Exception("Not implemented!")

    @staticmethod
    def _parse_soap_response(response):
        """Parse the ACS response and return a list of dictionary with ``{key:value}`` pair.

        Check for faultcode, HTTP error.
        In case none are found, parse the TR069 XML response data
        and return it in the form of a dictionary.

        :param response: XML response
        :type response: xml.etree.ElementTree
        :return: data
        :rtype: dict
        """
        raise Exception("Not implemented!")

    def _get_cmd_data(self, *args, **kwagrs):
        """Helper method to generate TR069 query.

        Fetch the CommandOptionsTypeStruct from WSDL of ACS
        i.e. ``ns0:CommandOptionsTypeStruct``
        """
        raise Exception("Not implemented!")

    def _get_class_data(self, *args, **kwagrs):
        """Helper method to generate TR069 query.

        Fetch the CPEIdentifierClassStruct from WSDL of ACS
        i.e. ``ns0:CPEIdentifierClassStruct``
        """
        raise Exception("Not implemented!")

    def _get_pars_val_data(self, p_arr_type, *args, **kwargs):
        """Helper method to generate TR069 query.

        Restructure values to be queried based on p_arr_type from WSDL of ACS
        """
        raise Exception("Not implemented!")

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
        raise Exception("Not implemented!")

    def close(self):
        """Implemention to close ACS connection."""
        raise Exception("Not implemented!")

    def GPA(self, param):
        """Get parameter attribute on ACS for the parameter specified.

        i.e. A remote procedure call (GetParameterAttribute).
        Example usage: ``acs_server.GPA('Device.WiFi.SSID.1.SSID')``

        :param param: parameter to be used in get
        :type param: string
        :returns: dictionary with keys Name, AccessList, Notification indicating the GPA
        :rtype: dict
        """
        raise Exception("Not implemented!")

    def SPA(self, param, **kwargs):
        """Get parameter attribute on ACS for the parameter specified.

        i.e a remote procedure call (GetParameterAttribute).
        Example usage : ``acs_server.SPA({'Device.WiFi.SSID.1.SSID':'1'})``
        could be parameter list of dicts/dict containing param name and notifications

        :param param: parameter to be used in set
        :type param: string
        :param kwargs : access_param,notification_param
        :returns: SPA response
        :rtype: dict
        """
        raise Exception("Not implemented!")

    def AddObject(self, param):
        """Add object ACS of the parameter specified i.e a remote procedure call (AddObject).

        :param param: parameter to be used to add
        :type param: string
        :raises assertion: On failure
        :returns: list of dictionary with key, value, type indicating the AddObject
        :rtype: dictionary
        """
        raise Exception("Not implemented!")

    def DelObject(self, param):
        """Delete object ACS of the parameter specified i.e a remote procedure call (DeleteObject).

        :param param: parameter to be used to delete
        :type param: string
        :returns: list of dictionary with key, value, type indicating the DelObject
        :rtype: string
        """
        raise Exception("Not implemented!")

    def GPV(self, param):
        """Get value from CM by ACS for a single given parameter key path synchronously.

        :param param: path to the key that assigned value will be retrieved
        :return: value as a dictionary
        """
        raise Exception("Not implemented!")

    def SPV(self, param_value):
        """Modify the value of one or more CPE Parameters.

        It can take a single k,v pair or a list of k,v pairs.
        :param param_value: dictionary that contains the path to the key and
        the value to be set. E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :return: status of the SPV as int (0/1)
        :raises: TR069ResponseError if the status is not (0/1)
        """
        raise Exception("Not implemented!")

    def GPN(self, param, next_level):
        """This method is used to  discover the Parameters accessible on a particular CPE

        :param param: parameter to be discovered
        :type param: string
        :next_level: displays the next level children of the object if marked true
        :type next_level: boolean
        :return: value as a dictionary
        """
        raise Exception("Not implemented!")

    def FactoryReset(self):
        """Execute FactoryReset RPC.

        Returns true if FactoryReset request is initiated.
        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the Reeboot of the device has to be handled in the test.

        :return: returns factory reset response
        """
        raise Exception("Not implemented!")

    def connectivity_check(self, cpeid):
        """Check the connectivity between the ACS and the DUT by\
        requesting the DUT to perform a schedule inform.

        NOTE: The scope of this method is to verify that the ACS and DUT can
        communicate with eachother!

        :param cpeid: the id to use for the ping
        :param type: string

        :return: True for a successful ScheduleInform, False otherwise
        """
        raise Exception("Not implemented!")

    def ScheduleInform(self, CommandKey="Test", DelaySeconds=20):
        """Execute ScheduleInform RPC

        :param commandKey: the string paramenter passed to scheduleInform
        :param type: string
        :param DelaySecond: delay of seconds in integer
        :param type: integer

        :return: returns ScheduleInform response
        """
        raise Exception("Not implemented!")

    def Reboot(self, CommandKey="Reboot Test"):
        """Execute Reboot.

        Returns true if Reboot request is initiated.

        :return: returns reboot RPC response
        """
        raise Exception("Not implemented!")

    def GetRPCMethods(self):
        """Execute GetRPCMethods RPC.

        :return: returns GetRPCMethods response of supported functions
        """
        raise Exception("Not implemented!")
