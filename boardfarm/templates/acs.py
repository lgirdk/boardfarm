"""Boardfarm LAN device template."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

# pylint: disable=invalid-name


class ACS(ABC):
    """Boardfarm LAN device template."""

    @abstractmethod
    def GPA(self, param: str) -> List[Dict]:
        """Get parameter attribute of the parameter specified.

        Example usage:

        >>> acs_server.GPA('Device.WiFi.SSID.1.SSID')

        :param param: parameter to be used in get
        :returns: dictionary with keys Name, AccessList, Notification indicating the GPA
        """
        raise NotImplementedError

    @abstractmethod
    def SPA(
        self, param: Union[List[Dict], Dict], **kwargs: Union[int, str]
    ) -> List[Dict]:
        """Set parameter attribute of the parameter specified.

        Example usage :

        >>> acs_server.SPA({'Device.WiFi.SSID.1.SSID':'1'}),

        could be parameter list of dicts/dict containing param name and notifications

        :param param: parameter to be used in set
        :param kwargs: access_param,access_list,notification_param
        :returns: SPA response
        """
        raise NotImplementedError

    @abstractmethod
    def GPV(self, param: str, timeout: int) -> List[Dict]:
        """Get value from CM by ACS for a single given parameter key path synchronously.

        :param param: path to the key that assigned value will be retrieved
        :param timeout: timeout in seconds
        :return: value as a list of dictionary
        """
        raise NotImplementedError

    @abstractmethod
    def SPV(self, param_value: Dict[str, Any], timeout: int) -> int:
        """Modify the value of one or more CPE Parameters.

        It can take a single k,v pair or a list of k,v pairs.

        :param param_value: dictionary that contains the path to the key and
            the value to be set. E.g. {'Device.WiFi.AccessPoint.1.AC.1.Alias':'mok_1'}
        :param timeout: to set the Lifetime Expiry time
        :return: status of the SPV as int (0/1)
        :raises: TR069ResponseError if the status is not (0/1)
        """
        raise NotImplementedError

    @abstractmethod
    def FactoryReset(self) -> List[Dict]:
        """Execute FactoryReset RPC.

        Note: This method only informs if the FactoryReset request initiated or not.
        The wait for the reboot of the device has to be handled in the test.

        :return: factory reset response
        """
        raise NotImplementedError

    @abstractmethod
    def Reboot(self, command_key: str) -> List[Dict]:
        """Execute Reboot.

        :return: reboot RPC response
        """
        raise NotImplementedError
