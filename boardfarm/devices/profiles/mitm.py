#!/usr/bin/env python3
"""Linux based DSLite server using ISC AFTR."""
import re
from ast import literal_eval

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
    base_exec_cmd = "mitmdump --mode transparent --showhost --set block_global=false"

    # this can be used to override behavior.
    # base device's method can be key.
    # e.g. Debian's configure method can call profile's configure method using self.profile['configure']
    profile = {}

    def __init__(self, *args, **kwargs):
        """To initialize the MITM container details."""
        self.quiet_mode = False
        self.mitm_pid = None
        self.mitm_dns_active = list()

        # Allow to skip re-executing iptable rules
        self.is_configured = kwargs.pop("mitm_configured", False)

        # allowing MITM to have access to all devices to intercept.
        self.dev_mgr = kwargs.get("mgr")
        self.intercepts = kwargs.pop("intercepts", {})

        self.log_name = self.dev_mgr.board.config.get_station() + ".mitm"
        self._tr069_ips = None

        MITM.configure_profile(self)

    def configure_mitm(self):
        """Install MITM proxy and configure iptable rules for each intercept."""

        # Note we'll implement interface configuration for later.
        # It will be too complex to maintain track of available intercept interfaces
        self.check_output("iptables -t nat -F")
        self.check_output("ip6tables -t nat -F")

        if "mitmproxy" not in self.check_output("pip3 freeze | grep mitmproxy"):
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

    def _set_dns_to_mitm(self, device_name: str) -> None:
        """Rewrite DNS entry on wan container to point to MITM'ed device
        if it is present in intercept block in ams.json/inventory server

        :param device_name: device name to be mitm'ed
        """
        try:
            mitmed_dns_entries = {
                f"{device_name}.boardfarm.com": [
                    self.intercepts[device_name]["v4"].split("; ")[-1],
                    self.intercepts[device_name]["v6"].split("; ")[-1],
                ]
            }
        except KeyError:
            raise KeyError(
                f"{device_name} is not found in intercepts block in the mitm config."
            )

        self.dev_mgr.wan.modify_dns_hosts(mitmed_dns_entries)
        self.mitm_dns_active.append(device_name)

    def _unset_dns_mitm(self, device_name: str) -> None:
        """Rollback DNS entry on wan container to point to real ACS server"""
        device = getattr(self.dev_mgr, device_name)
        host = f"{device_name}.boardfarm.com"
        if device:
            self.dev_mgr.wan.modify_dns_hosts(
                {host: device.dns.dnsv4[host] + device.dns.dnsv6[host]}
            )
            self.mitm_dns_active.remove(device_name)
        else:
            print(f"Device {device_name} is not found in device manager.")

    def start_capture(self, devices: list) -> None:
        """Add iptables rules if not done yet.
        Rewrite DNS for each provided device if not rewritten yet.
        Start capturing traffic in background to log file if not started yet.
        """
        if type(devices) is not list:
            raise TypeError(
                f"Expected devices parameter to be list, got {type(devices)} instead"
            )

        if not self.is_configured:
            self.configure_mitm()

        for device in set(devices) - set(self.mitm_dns_active):
            self._set_dns_to_mitm(device)

        if not self.mitm_pid:
            cmd = f"{MITM.base_exec_cmd} -w /root/{self.log_name} -q &"
            try:
                self.sendline(cmd)
                self.expect_prompt()
                self.mitm_pid = re.findall(r"\[\d+\]\s(\d+)", self.before).pop()
                self.expect(pexpect.TIMEOUT, timeout=1)

                # wait 1 second to check if process didn't get killed.
                running = self.check_output("")
                if "Exit" in running:
                    raise CodeError(
                        f"MITM pid:{self.pid} got killed.\nReason:\n{running}"
                    )
            except pexpect.TIMEOUT:
                raise CodeError()
        else:
            print(f"MITM is already running with pid {self.mitm_pid}")

    def stop_capture(self):
        """Rollback DNS for all mitm'ed devices.
        Kill mitm process on mitm container
        """
        for device in self.mitm_dns_active:
            self._unset_dns_mitm(device)
        self.check_output(f"kill {self.mitm_pid}")

    def get_tr069_headers(self, filter_str=None) -> [str, None]:
        """Return headers for last captured packet that comply with filter.

        :param filter_str: string to find in XML contents of tr069 packet.
        :return: dict with headers in case at least 1 packet found, None otherwise
        """
        filter_string = f"--set filter={filter_str}" if filter_str else ""
        cmd = (
            f"mitmdump -ns addons/tr069_reader.py -q -r {self.log_name} {filter_string}"
        )
        self.check_output(cmd)
        headers = re.findall(r"(?<=HEADERS:).*", self.before)
        if not headers:
            print(
                f"Did not find headers. Dump file is empty or no packets satisfy {filter_str} filter"
            )
            return
        headers = literal_eval(headers.pop().strip("\r"))
        return headers

    def get_tr069_body(self, filter_str=None):
        """Return body for last captured packet that comply with filter.

        :param filter_str: string to find in XML contents of tr069 packet.
        :return: dict with body in case at least 1 packet found, None otherwise
        """
        filter_string = f"--set filter='{filter_str}'" if filter_str else ""
        cmd = (
            f"mitmdump -ns addons/tr069_reader.py -q -r {self.log_name} {filter_string}"
        )
        self.check_output(cmd)
        bodies = re.findall(r"(?<=BODY:).*", self.before)
        if not bodies:
            print(
                f"Did not find body. Dump file is empty or no packets satisfy {filter_str} filter"
            )
            return
        body = literal_eval(bodies.pop().strip("\r"))
        return body
