from abc import ABC, abstractmethod


class TrafficGeneratorTemplate(ABC):
    """Traffic Generator template class.

    It is expected that the configuration object is parsed at __init__()

    All the methods are throwing an exception to ensure the derived class is
    properly implemented"""

    @abstractmethod
    def configure_lan_side(self):
        """Set up the appropriate number of actors on the CPE LAN side.

        This may take care of specific information such as IP addresses, VLAN IDs...
        """

        raise NotImplementedError

    @abstractmethod
    def configure_wan_side(self):
        """Set up the appropriate number of actors on the CPE WAN side.

        This may take care of specific information such as IP addresses, VLAN IDs...
        """
        raise NotImplementedError

    @abstractmethod
    def apply_traffic_profile(self, traffic_profile: str):
        """Apply the traffic profile specific for the test.

        I.e. load a specific test configuration file that is already present on the
        chassis.

        Here it is recommended to implement a translation between our test purpose and
        how the  script file is called on the device.
        I.e. we could use TR-398 as input to identify the request to run the traffic
        profile to meet Wi-Fi Residential & SOHO Performance Testing

        """
        raise NotImplementedError

    @abstractmethod
    def start_traffic(self):
        raise NotImplementedError

    @abstractmethod
    def stop_traffic(self):
        raise NotImplementedError

    @abstractmethod
    def fetch_results(self):
        """Fetch the results and return them in a device-agnostic way.

        It is responsibility of the test and not of the device to claim pass/failure
        based on the measured outcome."""
        raise NotImplementedError
