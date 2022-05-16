from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Union


@dataclass
class MIBInfo:
    """Dataclass for the MIBs defined either vendors specific or docsis mibs"""

    mib_name: str
    index: int
    type: str
    value: Union[str, int]


class MIBTemplate(ABC):
    @property
    @abstractmethod
    def vendor_prefix(self) -> str:
        raise NotImplementedError(
            "Vendor Prefix string must be defined for the gateway"
        )

    @property
    @abstractmethod
    def sw_method_mib(self) -> str:
        raise NotImplementedError(
            "SW Method MIB name supported by vendor must be defined for the gateway"
        )

    @property
    @abstractmethod
    def sw_server_address_mib(self) -> str:
        raise NotImplementedError(
            "SW Server Address MIB name supported by vendor must be defined for the gateway"
        )

    @property
    @abstractmethod
    def mfg_cvc(self) -> str:
        raise NotImplementedError(
            "Manufacturer CVC Details must be defined for the gateway"
        )

    @abstractmethod
    def get_sw_update_mibs(
        self,
        model: str,
        server_address: str,
        sw_file_name: str,
        protocol: int,
        admin_status: int,
        address_type: int,
        method: int = None,
    ) -> List[MIBInfo]:
        """returns the list of vendor specific mibs required for software update in cm config file

        :model: name of the gateway model eg: F3896LG, CH7465LG, etc
        :tye model: str
        :param server_address: ip address of the server
        :type server_address: str
        :param sw_file_name: name of the imgae file with extension
        :type sw_file_name: str
        :param protocol: protocol to be used by cm for sw download i.e 1 for tftp and 2 for http
        :type protocol: int
        :param admin_status: 1 for upgradeFromMgt, 2 for allowProvisioningUpgrade, 3 for ignoreProvisioningUpgrade
        :type admin_status: int
        :param address_type: type of ip address i.e 1 for ipv4 and 2 for ipv6
        :type address_type: int
        :param method: 1 for secure and 2 for unsecure download
        :type method: int
        :return: the list of all the docsis specific mibs with values passed as parameters
        :rtype: List[MIBInfo]
        """
        raise NotImplementedError(
            "Vendor Specific Software Update MIBs must be defined for the gateway"
        )
