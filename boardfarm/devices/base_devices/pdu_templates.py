from abc import abstractmethod
from typing import Any

from boardfarm.lib.signature_checker import __MetaSignatureChecker


class PDUTemplate(metaclass=__MetaSignatureChecker):
    """This class shows a basic set of interfaces to be implemented for PDU or Power under boardfarm devices"""

    def __init__(
        self,
        ip_address: str,
        username: str = None,
        password: str = None,
        conn_port: Any = None,
        outlet: str = None,
    ):
        """
        Base instance initialisation of the PDU. Used to store the necessary
        values that are then used by different PDU derived classes
        """
        self.ip_address = ip_address
        self.username = username
        self.password = password
        self.conn_port = conn_port
        self.outlet = outlet
        self.pcon = None

    @abstractmethod
    def _connect(self):
        """Method to define the connection with the PDU of the Device"""

    @abstractmethod
    def reset(self):
        """Method to define the implementation of reset functionality on PDU"""

    @abstractmethod
    def turn_off(self):
        """Method to define the implementation of turn-off functionality on PDU"""
