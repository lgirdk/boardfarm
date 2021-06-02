#!/usr/bin/env python3
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

try:
    import urllib as _urllib
    from urllib.error import HTTPError
    from urllib.request import urlopen
except Exception:
    from urllib2 import urlopen, HTTPError
    import urllib2 as _urllib

import inspect
import logging
import time
from typing import Any

import dlipower
import pexpect
from easysnmp import Session

from boardfarm.devices.base_devices.pdu_templates import PDUTemplate
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper

logger = logging.getLogger("bft")


def get_default_for_arg(function, arg):
    return inspect.getfullargspec(function)[3]


try:
    from ouimeaux.device.switch import Switch as WemoSwitch
    from ouimeaux.environment import Environment as WemoEnv
except Exception:
    WemoEnv = None
    WemoSwitch = None


def get_power_device(
    ip_address: str, username: str = None, password: str = None, outlet: str = None
):
    """Try to determine the type of network-controlled power switch\
    at a given IP address.

    Return a class that can correctly interact with that type of switch.
    """
    login_failed = False
    all_login_defaults = []
    for _name, obj in list(globals().items()):
        if inspect.isclass(obj) and issubclass(obj, PDUTemplate):
            defaults = get_default_for_arg(obj.__init__, "username")
            if defaults is not None and len(defaults) == 2:
                all_login_defaults.append((defaults[0], defaults[1]))

    if ip_address is None:
        if outlet is not None:
            if "wemo://" in outlet:
                if WemoEnv is None:
                    logger.error("Please install ouimeaux: pip install ouimeaux")
                else:
                    return WemoPowerSwitch(outlet=outlet)
            if "serial://" in outlet:
                return SimpleSerialPower(outlet=outlet)
            if "cmd://" in outlet:
                return SimpleCommandPower(outlet=outlet)
            if "px2://" in outlet:
                kwargs = {}
                if username:
                    kwargs["username"] = username
                if password:
                    kwargs["password"] = password
                return PX2(outlet=outlet, **kwargs)
            if "netio://" in outlet:
                return NetioPDU(outlet=outlet)

        return HumanButtonPusher()

    try:
        data = urlopen("http://" + ip_address).read().decode()
    except UnicodeDecodeError:
        data = urlopen("http://" + ip_address).read()
    except HTTPError as e:
        if str(e) == "HTTP Error 401: Unauthorized":
            login_failed = True

        # still try to read data
        data = e.read().decode()
    except Exception as e:
        logger.error(e)
        raise Exception("\nError connecting to %s" % ip_address)

    def check_data(data):
        if "<title>Power Controller" in data:
            return DLIPowerSwitch(
                ip_address, outlet=outlet, username=username, password=password
            )
        if "Sentry Switched CDU" in data:
            return SentrySwitchedCDU(ip_address, outlet=outlet)
        if "<title>APC " in data:
            return APCPower(ip_address, outlet=outlet)
        if "<b>IP9258 Log In</b>" in data:
            return Ip9258(ip_address, outlet, username=username, password=password)
        if "Cyber Power Systems" in data:
            return CyberPowerPdu(
                ip_address,
                port=outlet,
                outlet=outlet,
                username=username,
                password=password,
            )
        if "IP9820" in data:
            return Ip9820(ip_address, outlet)

        return None

    ret = check_data(data)
    if ret is not None:
        return ret

    if login_failed:
        # TODO: prioritize Ip9820 since it requires login?
        def get_with_username_password(username, password):
            # create a password manager
            password_mgr = _urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, "http://" + ip_address, username, password)
            handler = _urllib.request.HTTPBasicAuthHandler(password_mgr)
            opener = _urllib.request.build_opener(handler)
            opener.open("http://" + ip_address)
            _urllib.request.install_opener(opener)

            request = _urllib.request.Request("http://" + ip_address)
            response = opener.open(request)
            data = response.read()
            return data.decode("utf-8")

        # try with passed in info first
        ret = check_data(get_with_username_password(username, password))
        if ret is not None:
            return ret

        for username, password in all_login_defaults:
            try:
                ret = check_data(get_with_username_password(username, password))
            except Exception:
                continue
            else:
                break

        ret = check_data(data)
        if ret is not None:
            return ret

    raise Exception("No code written to handle power device found at %s" % ip_address)


class SentrySwitchedCDU(PDUTemplate):
    """Power Unit from Server Technology."""

    def __init__(
        self,
        ip_address: str,
        outlet: str,
        username: str = "admin",
        password: str = "admin",
    ):
        """Instance initialization."""
        super().__init__(ip_address, username, password, outlet=outlet)
        # Verify connection
        try:
            self._connect()
            self.pcon.sendline("status .a%s" % self.outlet)
            i = self.pcon.expect(
                ["Command successful", "User/outlet -- name not found"]
            )
            if i == 1:
                raise Exception("\nOutlet %s not found" % self.outlet)
            self.pcon.close()
        except Exception as e:
            logger.error(e)
            logger.error("\nError with power device %s" % self.ip_address)
            raise Exception("Error with power device %s" % self.ip_address)

    def _connect(self):
        pcon = bft_pexpect_helper.spawn("telnet %s" % self.ip_address)
        pcon.expect("Sentry Switched CDU Version", timeout=15)
        pcon.expect("Username:")
        pcon.sendline(self.username)
        pcon.expect("Password:")
        pcon.sendline(self.password)
        i = pcon.expect(["Switched CDU:", "Critical Alert"])
        if i == 0:
            self.pcon = pcon
        else:
            logger.error("\nCritical failure in %s, skipping PDU\n" % self.ip_address)
            raise Exception("critical failure in %s" % self.ip_address)

    def reset(self):
        """Connect to pdu, send reboot command."""
        retry_attempts = 2
        logger.info("\n\nResetting board %s %s" % (self.ip_address, self.outlet))
        for _ in range(retry_attempts):
            try:
                self._connect()
                self.pcon.sendline("reboot .a%s" % self.outlet)
                self.pcon.expect("Command successful")
                self.pcon.close()
                return
            except Exception as e:
                logger.error(e)
                continue
        raise Exception("\nProblem resetting outlet %s." % self.outlet)

    def turn_off(self):
        raise NotImplementedError


class PX2(PDUTemplate):
    """Power Unit from Raritan."""

    prompt = ["\\[.*\\] # ", "# "]

    def __init__(
        self, outlet: str, username: str = "admin", password: str = "scripter99"
    ):
        """Instance initialization."""
        ip_address, outlet = outlet.replace("px2://", "").split(";")
        super().__init__(ip_address, username, password, outlet=outlet)
        self._connect()

    def _connect(self):
        self.pcon = bft_pexpect_helper.spawn("telnet %s" % self.ip_address)
        self.pcon.expect(r"Login for PX\d CLI")
        self.pcon.expect("Username:")
        self.pcon.sendline(self.username)
        self.pcon.expect("Password:")
        self.pcon.sendline(self.password)
        self.pcon.expect(r"Welcome to PX\d CLI!")
        self.pcon.expect(self.prompt)

    def reset(self):
        try:
            self.pcon.sendline("")
            self.pcon.expect(self.prompt)
        except (pexpect.exceptions.EOF, pexpect.exceptions.TIMEOUT):
            logger.error("Telnet session has expired, establishing the session again")
            self._connect()
        self.pcon.sendline("power outlets %s cycle /y" % self.outlet)
        self.pcon.expect_exact("power outlets %s cycle /y" % self.outlet)
        self.pcon.expect(self.prompt)

        # no extraneous messages in console log
        assert not self.pcon.before.strip()

    def turn_off(self):
        try:
            self.pcon.sendline("")
            self.pcon.expect(self.prompt)
        except (pexpect.exceptions.EOF, pexpect.exceptions.TIMEOUT):
            logger.error("Telnet session has expired, establishing the session again")
            self._connect()
        self.pcon.sendline("power outlets %s off /y" % self.outlet)
        self.pcon.expect_exact("power outlets %s off /y" % self.outlet)
        self.pcon.expect(self.prompt)

        # no extraneous messages in console log
        assert not self.pcon.before.strip()


class NetioPDU(PDUTemplate):
    """Power Unit from Netio"""

    def __init__(self, outlet: str, username: str = "admin", password: str = "admin"):

        conn, outlet = outlet.replace("netio://", "").split(";")
        if ":" in conn:
            ip_address, conn_port = conn.split(":")
            super().__init__(ip_address, username, password, conn_port, outlet)
        else:
            super().__init__(conn, username, password, 23, outlet)

    def _connect(self):
        self.pcon = bft_pexpect_helper.spawn(
            f"telnet {self.ip_address} {self.conn_port}"
        )
        self.pcon.expect("100 HELLO 00000000 - KSHELL V1.5")
        self.pcon.sendline(f"login {self.username} {self.password}")
        self.pcon.expect("250 OK")

    def __quit(self):
        self.pcon.sendline("quit")
        self.pcon = None

    def reset(self):
        self._connect()
        self.pcon.sendline(f"port {self.outlet} 2")
        self.pcon.expect("250 OK")
        self.__quit()

    def turn_off(self):
        self._connect()
        self.pcon.sendline(f"port {self.outlet} 0")
        self.pcon.expect("250 OK")
        self.__quit()


class HumanButtonPusher(PDUTemplate):
    """Tell a person to physically reboot the router."""

    def __init__(self):
        """Instance initialization."""
        super().__init__(None)

    def _connect(self):
        raise NotImplementedError

    def reset(self):
        logger.info("\n\nUser power-cycle the device now!\n")

    def turn_off(self):
        logger.info("\n\nUser turn-off the device now!\n")


class APCPower(PDUTemplate):
    """A network-managed power unit from APC."""

    def __init__(
        self, ip_address: str, outlet: str, username: str = "apc", password: str = "apc"
    ):
        """Instance initialization."""
        super().__init__(ip_address, username, password, outlet=outlet)

    def _connect(self):
        self.pcon = bft_pexpect_helper.spawn("telnet %s" % self.ip_address)
        self.pcon.expect("User Name :")
        self.pcon.send(self.username + "\r\n")
        self.pcon.expect("Password  :")
        self.pcon.send(self.password + "\r\n")
        self.pcon.expect("> ")

    def reset(self):
        """Connect, login, and send commands to reset power on an outlet."""
        self._connect()
        self.pcon.send("1" + "\r\n")
        self.pcon.expect("> ")
        self.pcon.send("2" + "\r\n")
        self.pcon.expect("> ")
        self.pcon.send("1" + "\r\n")
        self.pcon.expect("> ")
        self.pcon.send(self.outlet + "\r\n")
        self.pcon.expect("> ")
        self.pcon.send("1" + "\r\n")
        self.pcon.expect("> ")
        self.pcon.send("6" + "\r\n")
        self.pcon.send("YES")
        self.pcon.send("" + "\r\n")
        self.pcon.expect("> ")

    def turn_off(self):
        raise NotImplementedError


class DLIPowerSwitch(PDUTemplate):
    """A network-managed power switch from Digital Loggers (DLI)."""

    def __init__(self, ip_address: str, outlet: str, username: str, password: str):
        """Instance initialization."""
        super().__init__(ip_address, username, password, outlet=outlet)
        self.switch = dlipower.PowerSwitch(
            hostname=ip_address, userid=username, password=password
        )

    def _connect(self):
        raise NotImplementedError

    def reset(self):
        """Turn an outlet off and then on."""
        self.switch.cycle(self.outlet)

    def turn_off(self):
        raise NotImplementedError


class WemoPowerSwitch(PDUTemplate):
    """Control a Wemo switch given an ipaddress."""

    def __init__(self, outlet: str):
        """Instance initialization."""
        addr = "http://" + outlet.replace("wemo://", "") + ":49153/setup.xml"
        super().__init__(None, outlet=addr)
        self.switch = WemoSwitch(self.outlet)

    def _connect(self):
        raise NotImplementedError

    def reset(self):
        """Turn an outlet off, wait 5 seconds, turn it back on."""
        self.switch.off()
        time.sleep(5)
        self.switch.on()

    def turn_off(self):
        raise NotImplementedError


class SimpleCommandPower(PDUTemplate):
    """Run a simple command to turn power on/off."""

    on_cmd = "true"
    off_cmd = "false"

    def __init__(self, outlet: str):
        """Instance initialization."""
        parsed = outlet.replace("cmd://", "").split(";")
        for param in parsed:
            for attr in ["on_cmd", "off_cmd"]:
                if attr + "=" in param:
                    setattr(self, attr, param.replace(attr + "=", "").encode())

    def _connect(self):
        raise NotImplementedError

    def reset(self):
        """Send off command, wait 5 seconds, send on command."""
        bft_pexpect_helper.spawn(self.off_cmd).expect(pexpect.EOF)
        time.sleep(5)
        bft_pexpect_helper.spawn(self.on_cmd).expect(pexpect.EOF)

    def turn_off(self):
        raise NotImplementedError


class SimpleSerialPower(PDUTemplate):
    """Simple serial based relay or power on off. Send a\
    string for "off" then "on" over serial."""

    serial_dev = "/dev/ttyACM0"
    baud = 2400
    off_cmd = b"relay on 0"
    delay = 5
    on_cmd = b"relay off 0"

    def __init__(self, outlet: str):
        """Instance initialization."""
        parsed = outlet.replace("serial://", "").split(";")
        self.serial_dev = "/dev/" + parsed[0]
        for param in parsed[1:]:
            for attr in ["on_cmd", "off_cmd"]:
                if attr + "=" in param:
                    setattr(self, attr, param.replace(attr + "=", "").encode())

    def _connect(self):
        raise NotImplementedError

    def reset(self):
        """Send off command, wait 5 seconds, send on command."""
        import serial

        with serial.Serial(self.serial_dev, self.baud) as set:
            if self.off_cmd is not None:
                set.write(self.off_cmd + "\r")
                time.sleep(5)

            set.write(self.on_cmd + "\r")

            set.close()

    def turn_off(self):
        raise NotImplementedError

    """
    IP Power 9258 networked power switch class.

    This work is released under the Creative Commons Zero (CC0) license.
    See http://creativecommons.org/publicdomain/zero/1.0/

    Example use:

    import time
    from ip9258 import Ip9258

    ip9258 = Ip9258('192.168.1.10', 'admin', 'password')

    for i in range(4):
        ip9258.on(i)
        time.delay(1)
        ip9258.off(i)
        time.delay(1)
    """


class Ip9258(PDUTemplate):
    """Network Power controller, IP Power 9258."""

    def __init__(
        self,
        ip_address: str,
        port: str,
        username: str = "admin",
        password: str = "12345678",
    ):
        """Instance initialization."""
        super().__init__(ip_address, username, password, port)
        self._connect()

    def _connect(self):
        # create a password manager
        password_mgr = _urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(
            None, "http://" + self.ip_address, self.username, self.password
        )
        handler = _urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = _urllib.request.build_opener(handler)
        # Now all calls to urllib2.urlopen use our opener.
        _urllib.request.install_opener(opener)

    def __on(self):
        """Send ON command."""
        logger.info("Power On Port(%s)\n" % self.conn_port)
        return _urllib.request.urlopen(
            "http://"
            + self.ip_address
            + "/set.cmd?cmd=setpower+p6"
            + str(self.conn_port)
            + "=1"
        )

    def __off(self):
        """Send OFF command."""
        logger.info("Power Off Port(%s)\n" % self.conn_port)
        return _urllib.request.urlopen(
            "http://"
            + self.ip_address
            + "/set.cmd?cmd=setpower+p6"
            + str(self.conn_port)
            + "=0"
        )

    def reset(self):
        """Turn off, wait 5 seconds, turn on."""
        self.__off()
        time.sleep(5)
        self.__on()

    def turn_off(self):
        """Send OFF command."""
        self.__off()


class CyberPowerPdu(PDUTemplate):
    """Power unit from CyberPower."""

    def __init__(
        self,
        ip_address: str,
        port: Any,
        username: str = "cyber",
        password: str = "cyber",
        outlet="",
    ):
        """Instance initialization."""
        super().__init__(
            ip_address,
            username,
            password,
            conn_port=port,
            outlet="1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4",
        )
        self.session = Session(hostname=self.ip_address, community="private", version=2)

    def _connect(self):
        raise NotImplementedError

    def __on(self):
        """Send ON command."""
        oid = self.outlet + "." + str(self.conn_port)
        self.session.set(oid, 1, "i")

    def __off(self):
        """Send OFF command."""
        oid = self.oid_Outlet + "." + str(self.conn_port)
        self.session.set(oid, 2, "i")

    def reset(self):
        """Send OFF command, wait 5 seconds, send ON command."""
        self.__off()
        time.sleep(5)
        self.__on()

    def turn_off(self):
        """Send OFF command"""
        self.__off()


class Ip9820(PDUTemplate):
    """Network Power controller, IP Power 9820."""

    def __init__(
        self,
        ip_address: str,
        port: Any,
        username: str = "admin",
        password: str = "12345678",
    ):
        """Instance initialization."""
        super().__init__(ip_address, username, password, conn_port=port)
        self._connect()

    def _connect(self):
        # create a password manager
        password_mgr = _urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(
            None, "http://" + self.ip_address, self.username, self.password
        )
        handler = _urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = _urllib.request.build_opener(handler)
        # Now all calls to _urllib.urlopen use our opener.
        _urllib.request.install_opener(opener)

    def __on(self):
        """Send ON command."""
        logger.info("Power On Port(%s)\n" % self.conn_port)
        return _urllib.request.urlopen(
            "http://"
            + self.ip_address
            + "/set.cmd?cmd=setpower+p6"
            + str(self.conn_port)
            + "=1"
        )

    def __off(self):
        """Send OFF command."""
        logger.info("Power Off Port(%s)\n" % self.conn_port)
        return _urllib.request.urlopen(
            "http://"
            + self.ip_address
            + "/set.cmd?cmd=setpower+p6"
            + str(self.conn_port)
            + "=0"
        )

    def reset(self):
        """Send OFF command, wait 5 seconds, sned ON command."""
        self.__off()
        time.sleep(5)
        self.__on()

    def turn_off(self):
        self.__off()


if __name__ == "__main__":
    logger.debug("Gathering info about power outlets...")

    if WemoEnv is not None:
        env = WemoEnv()
        env.start()
        scan_time = 10
        logger.debug("Scanning for WeMo switches for %s seconds..." % scan_time)
        env.discover(scan_time)
        if len(env.list_switches()) > 0:
            logger.debug("Found the following switches:")
            for switch_name in env.list_switches():
                switch = env.get_switch(switch_name)
                logger.debug("%s ip address is %s" % (switch_name, switch.host))
            logger.debug(
                "The switches above can be added by ip address" " for example use the"
            )
            logger.debug("following to use %s" % switch_name)
            logger.debug("\twemo://%s" % switch.host)
        else:
            logger.error("No WeMo switches found")
