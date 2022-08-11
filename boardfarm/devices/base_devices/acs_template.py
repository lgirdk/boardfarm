from abc import abstractmethod
from typing import Dict, List, Union

from boardfarm.lib.signature_checker import __MetaSignatureChecker

SpvObject = Dict[str, Union[str, int, bool]]
SpvStructure = List[SpvObject]


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

    @abstractmethod
    def GPV(self, cpe_id: str, parameter: str) -> None:
        """Send GetParamaterValues command via ACS server

        :param cpe_id: CPE idetifier.
        :param parameter: TR069 parameter to get values of.
        """

    @abstractmethod
    def SPV(self, cpe_id: str, key_value: SpvStructure) -> int:
        """Send SetParamaterValues command via ACS server.

        :param cpe_id: CPE idetifier.
        :param key_value: dictionary that contains the path to the key and the value to be set. E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :returns: integer status of command
        """
