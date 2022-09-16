from abc import abstractmethod
from typing import Dict, List, Optional, Union

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
