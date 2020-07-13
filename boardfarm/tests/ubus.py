# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import json
import time

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


def ubus_call_raw(payload, lan, ipaddr="192.168.1.1"):
    curl_cmd = "curl -d '%s' http://%s/ubus" % (json.dumps(payload), ipaddr)
    lan.sendline(curl_cmd)
    lan.expect("\r\n")
    lan.expect(prompt)

    return json.loads(lan.before)


def ubus_call(session_id, ubus_object, ubus_func, params, lan):
    j = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": [session_id, ubus_object, ubus_func, params],
    }
    return ubus_call_raw(j, lan)


def ubus_check_error(reply, lan, assert_on_err=True):
    if "error" in reply:
        print("Got error in reply")
        print(reply)

        assert not assert_on_err


def ubus_login_raw(lan, username="root", password="password"):
    json = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": [
            "00000000000000000000000000000000",
            "session",
            "login",
            {"username": username, "password": password},
        ],
    }
    return ubus_call_raw(json, lan)


def ubus_login_session(lan, username="root", password="password"):
    reply = ubus_login_raw(lan, username, password)

    ubus_check_error(reply, lan)

    return reply["result"][1]["ubus_rpc_session"]


def ubus_network_restart(session_id, lan):
    json = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": [session_id, "network", "restart", {}],
    }

    reply = ubus_call_raw(json, lan)
    ubus_check_error(reply, lan)


def ubus_system_reboot(session_id, lan):
    json = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": [session_id, "foo", "bar", {}],
    }

    reply = ubus_call_raw(json, lan)
    ubus_check_error(reply, lan)


class UBusTestNetworkRestart(rootfs_boot.RootFSBootTest):
    """Various UBus tests."""

    def runTest(self):
        lan = self.dev.lan

        for i in range(1000):
            print(
                "\nRunning iteration of ubus json-rpc network restart nubmer %s\n" % i
            )
            session_id = ubus_login_session(lan)
            print("\nLogged in with sessionid = %s\n" % session_id)
            ubus_network_restart(session_id, lan)
            # wait some amount of time, we can get a new session id before restart
            # really starts
            time.sleep(5)


class UBusTestSystemReboot(rootfs_boot.RootFSBootTest):
    """Various UBus tests."""

    def runTest(self):
        board = self.dev.board
        lan = self.dev.lan

        for i in range(1000):
            print("\nRunning iteration of ubus json-rpc system reboot nubmer %s\n" % i)
            session_id = ubus_login_session(lan)
            print("\nLogged in with sessionid = %s\n" % session_id)

            ubus_system_reboot(session_id, lan)
            board.wait_for_linux()
