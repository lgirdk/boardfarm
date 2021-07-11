from datetime import timedelta

from boardfarm.devices import base


class TrafficGenerator(base.BaseDevice):
    """TrafficGenerator Pseudo device class"""

    model = "base_traffic_generator"
    name = "traffic_gen"
    sign_check = True

    def __init__(self, *args, **kwargs):
        """Initialize a console/HTTP connection to traffic generator.

        :param ``*args``: model, conn_type
        :type ``*args``: tuple
        :param ``**kwargs``: configuration details for generator
        :type ``**kwargs``: dict
        """
        kwargs["start"] = ""
        self.consoles = []

        self.conn_cmd = kwargs.pop("conn_cmd", None)
        self.connection_type = kwargs.pop("connection_type", None)

        # provide expected speeds and latency to be configured in a project.
        self.tcp_down_speed = kwargs.pop("tcp_down_speed", None)
        self.tcp_up_speed = kwargs.pop("tcp_up_speed", None)
        self.udp_down_speed = kwargs.pop("udp_down_speed", None)
        self.udp_up_speed = kwargs.pop("udp_up_speed", None)
        self.down_latency = timedelta(
            microseconds=kwargs.pop("down_latency_ns", 10000000) / 1000.0
        )
        self.up_latency = timedelta(
            microseconds=kwargs.pop("up_latency_ns", 10000000) / 1000.0
        )

        # Store instances of TrafficGeneratorPort as client or server
        self.server = None
        self.client = None
        self.results = {}

        # parse or store port configurations from a project
        self.port_config = {}

    def check_status(self):
        """Verify client and server ports are online and ready to run traffic.

        :return: True or False
        :rtype: bool
        """
        raise NotImplementedError

    def touch(self):
        # No need to keep the console alive
        raise NotImplementedError

    def close(self):
        """Close connection to traffic generator"""
        raise NotImplementedError

    def reset(self, **kwargs):
        """Reset settings done to client or server ports.

        Can also be done via a power reset.
        """
        raise NotImplementedError

    def __str__(self):
        return f"""
        TCP
            Down speed: {self.tcp_down_speed}
            UP speed:   {self.tcp_up_speed}
        UDP
            Down speed: {self.udp_down_speed}
            UP speed:   {self.udp_up_speed}
        LATENCY:
            DOWN:       {self.down_latency}
            UP:         {self.up_latency}
        """

    def load_project(self, project):
        """In case of pre-defined project, following method is used to load configurations

        Project must be parsed and loaded in the form of a dict.
        In case of loading a project, all expected traffic parameters must be updated.

        :param project: File path of project to be loaded
        :type project: str
        :return: Dictionary of configuratios for TG
        :rtype: dict
        """
        raise NotImplementedError

    def update_project(self, project):
        """Apply settings of a project to the traffic generator.

        :param project: File path of project to be loaded
        :type project: str
        """
        config = self.load_project(project)
        for _conf, _value in config.items():
            # decide to add server_port / client_port / wifi_port
            # e.g.
            raise NotImplementedError
        raise NotImplementedError

    def add_server_port(self, address, port, interface, protocol):
        """Initialize a server port.

        :param address: ip address details for port
        :type address: str
        :param port: port id of traffic generator
        :type port: str
        :param interface: interface on chassis, gige/xgige
        :type interface: str
        :param protocol: TCP or UDP
        :type protocol: str
        """
        raise NotImplementedError

    def remove_server_port(self, port):
        """ "Reset server port"""
        raise NotImplementedError

    def add_client_port(self, address, port, interface, protocol):
        """Initialize a client port.

        :param address: ip address details for port
        :type address: str
        :param port: port id of traffic generator
        :type port: str
        :param interface: interface on chassis, gige/xgige
        :type interface: str
        :param protocol: TCP or UDP
        :type protocol: str
        """
        raise NotImplementedError

    def remove_client_port(self, port):
        """Reset client port"""
        raise NotImplementedError

    def add_wifi_port(self, address, port, interface, ssid, protocol):
        """Initialize a Wi-Fi client port.

        :param address: ip address details for port
        :type address: str
        :param port: port id of traffic generator
        :type port: str
        :param interface: interface on chassis, gige/xgige
        :type interface: str
        :param ssid: WIFI SSID to connect to.
        :type ssid: str
        :param protocol: TCP or UDP
        :type protocol: str
        """
        raise NotImplementedError

    def remove_wifi_port(self, port):
        """reset WIFI port"""
        raise NotImplementedError

    def run_traffic_gen(self, flow_direction="down"):
        """Initiate traffic flow based on direction provided as arg.

        Need to ensure that client and server ports are configured.
        Based on flow direction, port need to be assigned and configured.

        TODO: figure out implementation for bi-directional

        :param flow_direction: Upstream or Downstream
        :type flow_direction: str
        """
        raise NotImplementedError

    def run_status(self, *args, **kwargs):
        """Fetch execution details created by run_traffic_gen"""
        raise NotImplementedError

    def get_results(self):
        """Fetch execution results.

        Fetch execution status, and verify if result is generated.
        Throw an exception in case result is not generated.
        """
        raise NotImplementedError

    @staticmethod
    def get_flow_details(results, protocol, flow_direction="down"):
        """Parse results for verification of tests."""
        raise NotImplementedError


class TrafficGeneratorPort(object):
    """Pseudo base class for configuring a port on traffic genrator"""

    def __init__(self, *args, **kwargs):
        self.port_name = kwargs.pop("role", "server")
        self.address = kwargs.pop("address", None)
        self.port = kwargs.pop("port", None)
        self.interface = kwargs.pop("interface", None)
        self.ssid = kwargs.pop("ssid", None)
        self.protocol = kwargs.pop("protocol", "TCP")

    def check_status(self):
        """Ensure if port is configurared, ARP is resolved and pingable"""
        raise NotImplementedError

    def __str__(self):
        return f'Port "{self.port_name}" ({self.interface}@{self.address})'
