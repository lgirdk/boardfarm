#!/usr/bin/env python3
"""Linux based DSLite server using ISC AFTR."""
import re

import pexpect

from boardfarm.devices.profiles import base_profile
from boardfarm.exceptions import CodeError
from boardfarm.lib.installers import apt_install


class MITM(base_profile.BaseProfile):
    """MITM profile for Debian Based Devices.

    Assumptions:
    - All interfaces are configured with IP address statically
    - veth pair interfaces for intercepting devices already exist.
    """

    model = "mitm"
    aftr_dir = "/root/addons/"
    base_exec_cmd = "mitmdump --mode transparent --showhost --set global_block=false"

    # this can be used to override behavior.
    # base device's method can be key.
    # e.g. Debian's configure method can call profile's configure method using self.profile['configure']
    profile = {}

    def __init__(self, *args, **kwargs):
        """To initialize the MITM container details."""
        self.quiet_mode = False
        self.mitm_pid = None

        # Allow to skip re-executing iptable rules
        self.is_configured = kwargs.pop("mitm_configured", False)

        # allowing MITM to have access to all devices to intercept.
        self.dev_mgr = kwargs.get("mgr")
        self.intercepts = kwargs.pop("intercepts", {})

        MITM.configure_profile(self)

    def configure_mitm(self):
        """Install MITM proxy and configure iptable rules for each intercept."""

        # Note we'll implement interface configuration for later.
        # It will be too complex to maintain track of available intercept interfaces
        self.check_output("iptables -t nat -F")
        self.check_output("ip6tables -t nat -F")

        if "mitmproxy" in self.check_output("pip3 freeze | grep mitmproxy"):
            apt_install(self, "python3-dev python3-pip libffi-dev libssl-dev")
            self.check_output("pip3 install mitmproxy")

        for _, val in self.intercepts.items():
            v4 = val.get("v4", "")
            if v4:
                v4 = [i.strip() for i in v4.split(";")]
                self.check_output(
                    f"iptables -t nat -A PREROUTING -i eth1 -p tcp --destination {v4[-1]} -j REDIRECT --to-port 8080"
                )
                self.check_output(
                    f"iptables -t nat -A PREROUTING -i {v4[0]} -p tcp --source {v4[-1]} -j REDIRECT --to-port 8080"
                )

            v6 = val.get("v6", "")
            if v6:
                v6 = [i.strip() for i in v6.split(";")]
                self.check_output(
                    f"ip6tables -t nat -A PREROUTING -i eth1 -p tcp --destination {v6[-1]} -j REDIRECT --to-port 8080"
                )
                self.check_output(
                    f"ip6tables -t nat -A PREROUTING -i {v6[0]} -p tcp --source {v6[-1]} -j REDIRECT --to-port 8080"
                )

        self.is_configured = True

    def configure_dns_server(self):
        """DNS should be updated only before running before mitm"""
        pass

    def run_mitm_proxy(self, log=None, script=None):
        if not self.is_configured:
            self.configure_mitm()

        cmd = MITM.base_exec_cmd
        if log:
            cmd = f"{cmd} -w /root/{log}"
            self.quiet_mode = True
        if script:
            cmd = f"{cmd} -s {script}"

        try:
            if self.quiet_mode:
                self.sendline(f"{cmd} -q &")
                self.expect_prompt()
                self.mitm_pid = re.findall(r"\[\d+\]\s(\d+)", self.before).pop()
                self.expect(pexpect.TIMEOUT, timeout=1)

                # wait 1 second to check if process didn't get killed.
                running = self.check_output("")
                if "Exit" in running:
                    raise CodeError(
                        f"MITM pid:{self.pid} got killed.\nReason:\n{running}"
                    )
            else:
                self.sendline(f"{cmd} -v")
                if (
                    self.expect(
                        [r"Proxy server listening at http:.*:8080"] + self.prompt,
                        timeout=5,
                    )
                    != 0
                ):
                    raise CodeError(
                        f"MITM process did not start.\nReason :\n{self.before}"
                    )
        except pexpect.TIMEOUT:
            raise CodeError()

        self.kill_mitm = True

    def kill_mitm_proxy(self):
        out = None
        if self.kill_mitm:
            if self.mitm_pid:
                self.check_output(f"kill {self.mitm_pid}")
                self.check_output("")
            else:
                self.sendcontrol("c")
                self.expect_prompt()
                out = self.before
            self.kill_mitm = False
        return out
