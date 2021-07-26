"""Provide Hook implementations for contingency checks."""


import logging

from nested_lookup import nested_lookup

from boardfarm.exceptions import ContingencyCheckError
from boardfarm.lib.common import check_prompts, domain_ip_reach_check
from boardfarm.lib.DeviceManager import device_type
from boardfarm.lib.hooks import contingency_impl, hookimpl
from boardfarm.plugins import BFPluginManager

logger = logging.getLogger("tests_logger")


class ContingencyCheck:
    """Contingency check implementation."""

    impl_type = "base"

    @hookimpl(tryfirst=True)
    def contingency_check(self, env_req, dev_mgr, env_helper):
        """Register service check plugins based on env_req.

        Reading the key value pairs from env_req, BFPluginManager scans
        for relative hook specs and implementations and loads them into a
        feature PluginManager (use generate_feature_manager).

        Once all plugins are registered, this functions will call the hook
        initiating respective service checks.

        :param env_req: ENV request provided by a test
        :type env_req: dict
        """

        logger.info("Executing all contingency service checks under boardfarm")
        # initialize a feature Plugin Manager for Contingency check
        pm = BFPluginManager("contingency")
        # this will load all feature hooks for contingency
        pm.load_hook_specs("feature")
        all_impls = pm.fetch_impl_classes("feature")

        plugins_to_register = [all_impls["boardfarm.DefaultChecks"]]

        # referencing this from boardfarm-lgi
        dns_env = nested_lookup("DNS", env_req.get("environment_def", {}))
        if dns_env:
            plugins_to_register.append(all_impls["boardfarm.DNS"])

        # ACS reference from boardfarm-lgi
        if "tr-069" in env_req.get("environment_def", {}):
            plugins_to_register.append(all_impls["boardfarm.ACS"])

        plugins_to_register.append(all_impls["boardfarm.CheckInterface"])

        # since Pluggy executes plugin in LIFO order of registration
        # reverse the list so that Default check is executed first
        for i in reversed(plugins_to_register):
            pm.register(i)
        result = pm.hook.service_check(
            env_req=env_req, dev_mgr=dev_mgr, env_helper=env_helper
        )

        # this needs to be orchestrated by hook wrapper maybe
        BFPluginManager.remove_plugin_manager("contingency")
        return result


class DefaultChecks:
    """Perform these checks even if ENV req is empty."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr, env_helper):
        """Implement Default Contingency Hook."""

        logger.info("Executing Default service check [check_prompts] for BF")

        provisioner = dev_mgr.by_type(device_type.provisioner)
        wan = dev_mgr.by_type(device_type.wan)
        sipserver = dev_mgr.by_type(device_type.sipcenter)
        softphone = dev_mgr.by_type(device_type.softphone)

        wan_devices = [wan, provisioner]
        lan_devices = []

        voice = "voice" in env_req.get("environment_def", {})
        if voice:
            lan_devices = [dev_mgr.lan, dev_mgr.lan2]
            wan_devices = [wan, provisioner, sipserver, softphone]

        check_prompts(wan_devices + lan_devices)

        logger.info("Default service check [check_prompts] for BF executed")


class CheckInterface:
    """Perform these checks even if ENV req is empty."""

    impl_type = "feature"

    @contingency_impl(trylast=True)
    def service_check(self, env_req, dev_mgr, env_helper):
        """Implement Default Contingency Hook."""

        logger.info("Executing CheckInterface service check for BF ")

        ip = {}
        wan = dev_mgr.by_type(device_type.wan)
        amount_of_clients_to_be_tested = len(
            env_req.get("environment_def", {}).get("board", {}).get("lan_clients", [])
        )
        lan_devices = dev_mgr.lan_clients[:amount_of_clients_to_be_tested]

        def call_lan_clients(dev, flags, **kwargs):
            ip_lan = {}
            call = {
                "ipv4": dev.start_ipv4_lan_client,
                "ipv6": dev.start_ipv6_lan_client,
            }
            for i in flags:
                out = call[i](**kwargs)
                assert out, f"{dev.name} failed to get {i} address!!"
                ip_lan[i] = out
                # We need to restart DUT interface only once
                kwargs["prep_iface"] = False
            ip[dev.name] = ip_lan

        prov_mode = env_helper.get_prov_mode() if env_helper.has_prov_mode() else "dual"
        flags = []

        flags.append("ipv4")
        if prov_mode != "ipv4":
            flags.append("ipv6")

        for dev in lan_devices:
            dev.configure_docker_iface()
            call_lan_clients(dev, flags, prep_iface=True)
            dev.configure_proxy_pkgs()

        def _setup_as_wan_gateway():
            ipv4 = wan.get_interface_ipaddr(wan.iface_dut)
            ipv6 = wan.get_interface_ip6addr(wan.iface_dut)
            return {"ipv4": ipv4, "ipv6": ipv6}

        ip["wan"] = _setup_as_wan_gateway()

        logger.info("CheckInterface service checks for BF executed")

        return ip


class DNS:
    """DNS contingency checks."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Contingency Hook for DNS."""

        logger.info("Executing DNS service check for BF")

        board = dev_mgr.by_type(device_type.DUT)
        dns_env = nested_lookup("DNS", env_req["environment_def"])
        if nested_lookup("ACS_SERVER", dns_env):
            acs_dns = dns_env[0]["ACS_SERVER"]

        if acs_dns:
            output = board.dns.nslookup("acs_server.boardfarm.com")
            domain_ip_reach_check(
                board.arm,
                acs_dns["ipv4"]["reachable"] + acs_dns["ipv6"]["reachable"],
                acs_dns["ipv4"]["unreachable"] + acs_dns["ipv6"]["unreachable"],
                output,
            )

        logger.info("DNS service checks for BF executed")


class ACS:
    """ACS contingency checks."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Contingency Hook for ACS."""

        logger.info("Executing ACS service check for BF")

        acs_server = dev_mgr.by_type(device_type.acs_server)
        packet_analysis = "packet_analysis" in env_req["environment_def"]["tr-069"]

        board = dev_mgr.by_type(device_type.DUT)
        if not board._cpeid:
            board.get_cpeid()

        def check_acs_connection():
            return bool(acs_server.GPV("Device.DeviceInfo.SoftwareVersion"))

        acs_connection = check_acs_connection()
        if not acs_connection:
            raise ContingencyCheckError("ACS service check Failed.")

        if packet_analysis:

            def check_packet_analysis_enable():
                return acs_server.session_connected

            check_packet_analysis_enable()

        logger.info("ACS service checks for BF executed")
