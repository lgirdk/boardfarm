"""Provide Hook implementations for contingency checks."""


import logging

from nested_lookup import nested_lookup

from boardfarm.lib.common import (
    check_prompts,
    domain_ip_reach_check,
    retry_on_exception,
)
from boardfarm.lib.DeviceManager import device_type
from boardfarm.lib.hooks import contingency_impl, hookimpl
from boardfarm.plugins import BFPluginManager

logger = logging.getLogger("bft")


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
        # Print statement can be removed later. Kept for understand exec flow
        print("This is BF contingency check")
        print("Executing all service checks under boardfarm")

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
        # Voice reference from boardfarm-lgi
        if "voice" in env_req.get("environment_def", {}):
            plugins_to_register.append(all_impls["boardfarm.Voice"])

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
        print("Executing Default service check for BF", end=("\n" + "-" * 80 + "\n"))

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

        print("Default service checks for BF executed", end=("\n" + "-" * 80 + "\n"))


class CheckInterface:
    """Perform these checks even if ENV req is empty."""

    impl_type = "feature"

    @contingency_impl(trylast=True)
    def service_check(self, env_req, dev_mgr, env_helper):
        """Implement Default Contingency Hook."""
        print(
            "Executing service check for BF CheckInterface",
            end=("\n" + "-" * 80 + "\n"),
        )

        ip = {}
        wan = dev_mgr.by_type(device_type.wan)
        # TODO: should be driven by env_req
        lan_devices = [dev_mgr.lan, dev_mgr.lan2]

        def _start_lan_client(dev):
            ipv4, ipv6 = retry_on_exception(dev.start_lan_client, [], retries=1)
            return {"ipv4": ipv4, "ipv6": ipv6}

        def _setup_as_wan_gateway():
            ipv4 = wan.get_interface_ipaddr(wan.iface_dut)
            ipv6 = wan.get_interface_ip6addr(wan.iface_dut)
            return {"ipv4": ipv4, "ipv6": ipv6}

        for dev in lan_devices:
            ip[dev.name] = _start_lan_client(dev)
        ip["wan"] = _setup_as_wan_gateway()

        print(
            "Service checks for BF CheckInterface executed",
            end=("\n" + "-" * 80 + "\n"),
        )

        return ip


class DNS:
    """DNS contingency checks."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Contingency Hook for DNS."""
        print("Executing service check for DNS", end=("\n" + "-" * 80 + "\n"))

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


class ACS:
    """ACS contingency checks."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Contingency Hook for ACS."""
        print("Executing service check for ACS", end=("\n" + "-" * 80 + "\n"))

        board = dev_mgr.by_type(device_type.DUT)
        acs_server = dev_mgr.by_type(device_type.acs_server)

        packet_analysis = "packet_analysis" in env_req["environment_def"]["tr-069"]

        def check_acs_connection():
            return bool(
                acs_server.get(board.get_cpeid(), "Device.DeviceInfo.SoftwareVersion")
            )

        check_acs_connection()

        if packet_analysis:

            def check_packet_analysis_enable():
                return acs_server.session_connected

            check_packet_analysis_enable()

        print("ACS service checks  executed", end=("\n" + "-" * 80 + "\n"))


class Voice:
    """VOICE contingency checks."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Contingency Hook for VOICE."""
        print("Executing service check for Voice", end=("\n" + "-" * 80 + "\n"))

        dev_mgr.lan.check_tty()
        dev_mgr.lan2.check_tty()
        dev_mgr.board.mta_prov_check()
        dev_mgr.board.check_sip_endpoints_registration()

        print("Voice service checks for BF executed", end=("\n" + "-" * 80 + "\n"))
