"""Provide Hook specifications for contingency checks."""

from boardfarm.lib.specs import contingency_spec, hookspec


class ContingencyCheck:
    """Base class for Contingency check."""

    spec_type = "base"

    @hookspec
    def contingency_check(self, env_req, dev_mgr, env_helper):
        """Perform contingency checks based on key-value pair in ENV req.

        :param env_req: ENV request provided by a test
        :type env_req: dictionary
        """


class ServiceCheck:
    """Base class for Service checks done inside Contingency checks."""

    spec_type = "feature"

    @contingency_spec
    def service_check(self, env_req, dev_mgr, env_helper):
        """Validate a service based on ENV params provded by Contingency Check.

        :param env_params: key-value pair for particular service
        :type env_params: dictionary
        """
