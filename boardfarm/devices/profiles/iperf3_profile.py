#!/usr/bin/env python3

from collections import namedtuple

from boardfarm.devices.profiles import base_profile
from boardfarm.exceptions import CodeError, DeviceDoesNotExistError


class IPerf3(base_profile.BaseProfile):

    # mandatory class attributes for profile
    model = "iperf3"
    profile = {}

    # there can be a better approach. The data transfer units in iperf output is not uniform.
    # using the conversion below to set data in Mbps rate.
    units = {
        "bits": 1,
        "bytes": 8,
        "kbits": 1024 * 1,
        "kbytes": 1024 * 8,
        "mbits": 1024 * 1024 * 1,
        "mbytes": 1024 * 1024 * 8,
        "gbits": 1024 * 1024 * 1024 * 1,
        "gbytes": 1024 * 1024 * 1024 * 8,
    }

    def __init__(self, *args, **kwargs):
        """Constructor method to initialize the container details
        """
        self.iperf_server_data = []
        self.iperf_client_data = []
        self.first_iteration = {"server": True, "client": True}
        iperf_details = namedtuple(
            "Iperf3Data", ["role", "daemon_mode", "logfile", "extra_opts", "port"]
        )

        # for server or client
        role = kwargs.pop("role", "server")
        daemon_mode = kwargs.pop("daemon", False)
        logfile = kwargs.pop("logfile", None)
        extra_opts = kwargs.pop("extra_opts", "")

        # setting port for client makes less sense, as its dependent on server
        # allowing flexibility to opt for it in case of negative scenarios
        port = kwargs.pop("iperf3_port", None)

        self.iperf_profile_args = iperf_details(
            role, daemon_mode, logfile, extra_opts, port
        )
        IPerf3.configure_profile(self)
        IPerf3.init_iperf_args(self)

    ####################################################################################################
    # class methods
    ####################################################################################################

    @classmethod
    def init_iperf_args(cls, device):
        args = device.iperf_profile_args

        if args.role == "server":
            data = namedtuple(
                "IperfServer",
                ["device", "daemon_mode", "logfile", "extra_opts", "port"],
            )
            IPerf3.profile["server"] = data(
                device, args.daemon_mode, args.logfile, args.extra_opts, args.port
            )
        elif args.role == "client":
            data = namedtuple(
                "IperfClient",
                ["device", "daemon_mode", "logfile", "extra_opts", "port"],
            )
            IPerf3.profile["client"] = data(
                device, args.daemon_mode, args.logfile, args.extra_opts, args.port
            )

    @classmethod
    def run_traffic_gen(cls, traffic_profile="TCP", duration=10):
        client_args = cls.get_traffic_gen_client()
        client = client_args.device

        server_args = cls.get_traffic_gen_server()
        server = server_args.device
        port = server_args.port

        print("Run Traffic Generation Parameters:\n"
              f"Profile: {traffic_profile}\n"
              f"Server: {server.name}:{port}\n"
              f"Client: {client.name}\n")
        raise CodeError("Not Implemented !!")

    @classmethod
    def get_traffic_gen_client(cls):
        try:
            client = cls.profile["client"]
            return client
        except KeyError:
            raise DeviceDoesNotExistError(
                "Client not found!!" "Check json config for client profile"
            )

    @classmethod
    def get_traffic_gen_server(cls):
        try:
            server = cls.profile["server"]
            return server
        except KeyError:
            raise DeviceDoesNotExistError(
                "Server not found!!"
                "Check json config for server profile")

####################################################################################################
