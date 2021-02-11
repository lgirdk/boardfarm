"""Provide Hook implementations for contingency checks."""

from nested_lookup import nested_lookup

from boardfarm.lib.hooks import contingency_impl, hookimpl
from boardfarm.plugins import BFPluginManager


class ContingencyCheck:
    """Contingency check implementation."""

    impl_type = "base"

    @hookimpl(tryfirst=True)
    def contingency_check(self, env_req, dev_mgr):
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
        # TODO: Add right set of rules here.
        # start registering service check plugin based on ENV Req

        # referencing this from boardfarm-lgi
        dns_env = nested_lookup("DNS", env_req.get("environment_def", {}))
        if dns_env:
            plugins_to_register.append(all_impls["boardfarm.DNS"])

        # ACS reference from boardfarm-lgi
        if "tr-069" in env_req.get("environment_def", {}):
            plugins_to_register.append(all_impls["boardfarm.ACS"])

        # since Pluggy executes plugin in LIFO order of registration
        # reverse the list so that Default check is executed first
        for i in reversed(plugins_to_register):
            pm.register(i)
        pm.hook.service_check(env_req=env_req, dev_mgr=dev_mgr)

        # this needs to be orchestrated by hook wrapper maybe
        BFPluginManager.remove_plugin_manager("contingency")


class DefaultChecks:
    """Perform these checks even if ENV req is empty."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Default Contingency Hook."""
        print("Default service checks executed", end=("\n" + "-" * 80 + "\n"))


class DNS:
    """DNS contingency checks."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Contingency Hook for DNS."""
        print("Executing service check for DNS", end=("\n" + "-" * 80 + "\n"))


class ACS:
    """ACS contingency checks."""

    impl_type = "feature"

    @contingency_impl
    def service_check(self, env_req, dev_mgr):
        """Implement Contingency Hook for ACS."""
        print("Executing service check for ACS", end=("\n" + "-" * 80 + "\n"))
