# !/usr/bin/env python
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import multiprocessing
import os
import platform
import re
import socket
import sys
import time
import warnings

import distro
import requests
from boardfarm.lib.common import run_once


class ServerError(Exception):
    """Exception for server error."""

    pass


class BoardfarmWebClient(object):
    """Handle interacting with a boardfarm server.

    For checking out stations, etc.
    """
    def __init__(self, config_url, bf_version="1.0.0", debug=False):
        """Instance initialisation."""
        self.config_url = config_url
        self.bf_version = bf_version
        self.debug = debug
        self.server_url = None
        self.server_version = None
        self.checked_out = None
        self.bf_config_str = None
        self.bf_config = None
        # If config isn't on a server, do nothing
        if not config_url.startswith("http"):
            return
        self.headers = {"user-agent": self._user_agent()}
        self.default_data = {
            "hostname":
            socket.gethostname(),
            "username":
            os.environ.get("BUILD_USER_ID", None)
            or os.environ.get("USER", None),
            "build_url":
            os.environ.get("BUILD_URL", None),
        }
        if self.default_data["username"] in [
                "root",
                "testuser",
                "tester",
                "docker-factory",
                "boardfarm",
        ]:
            warnings.warn(
                "Warning! Usernames 'root', 'testuser', 'tester', 'docker-factory', 'boardfarm' are blacklisted. Use either firstname or the git Id as username. E.g. If the name is Tom Smith, Tom or tsmith could be used."
            )
            raise ServerError(
                "\x1b[6;30;42m" +
                "------------Username {} is blacklisted-----------".format(
                    self.default_data["username"]) + "\x1b[0m")
        try:
            res = requests.get(self.config_url,
                               headers=self.headers,
                               timeout=5)
            self.bf_config_str = res.text
            self.bf_config = res.json()
            res.raise_for_status()
        except Exception as e:
            if self.bf_config:
                raise ServerError(self.bf_config.get("message", ""))
            else:
                raise e
        try:
            # See if this is a boardfarm server by checking the root /api path
            self.server_url = re.search("http.*/api", self.config_url).group(0)
            r = requests.get(self.server_url, headers=self.headers, timeout=5)
            data = r.json()
            self.server_version = data.get("version", None)

            @run_once
            def print_info():
                print("Using %s as boardfarm server, version %s" %
                      (self.server_url, self.server_version))

            print_info()
        except Exception as e:
            if self.debug:
                print(e)
                print("The server hosting '%s' does not appear to be a "
                      "boardfarm server." % self.config_url)

    def _user_agent(self):
        bfversion = "Boardfarm %s" % self.bf_version
        s = platform.system()
        py = "Python %s.%s.%s" % (sys.version_info[:3])
        try:
            system = platform.system()
            if system == "Linux":
                s = "%s %s" % distro.linux_distribution()[:2]
            elif system == "Darwin":
                s = "MacOS %s" % platform.mac_ver()[0]
            elif system == "Windows":
                s = "Windows %s" % platform.win32_ver()[0]
        except Exception as e:
            if self.debug:
                print(e)
                print("Unable to get more specific system info")
        return ";".join([bfversion, py, s])

    def _poll(self, done, seconds=60):
        """Periodically let the server know we are still alive and using things."""
        time.sleep(seconds)
        while not done.is_set():
            url = self.server_url + "/checkout"
            requests.post(url, json=self.checked_out, headers=self.headers)
            time.sleep(seconds)

    def post_temp_message(self, msg):
        """Post a temporary message.

        Use this to post a temporary message visible on the server only
        while you have a station checked out.
        The server clears these temporary messages when station is checked in.
        """
        if not self.server_version or not self.checked_out:
            return
        try:
            url = self.server_url + "/stations/" + self.checked_out["name"]
            requests.post(url,
                          json={"_meta.active_msg": msg},
                          headers=self.headers)
        except Exception as e:
            if self.debug:
                print(e)
                print("Failed to notify boardfarm server with message.")

    def post_note(self, name, note):
        """Post note.

        If an error is encountered with a station, use this function
        to send a message to the boardfarm server. Something short
        and useful for display.
        """
        if not self.server_version:
            return
        try:
            url = self.server_url + "/stations/" + name
            requests.post(url, json={"note": note}, headers=self.headers)
        except Exception as e:
            if self.debug:
                print(e)
                print("Failed to notify boardfarm server with message.")

    def checkout(self, config):
        if not self.server_version:
            return
        try:
            # Gather all the '_id' keys out of the config
            station_id = config.get("_id", None)
            device_ids = []
            if "devices" in config:
                device_ids = [
                    x["_id"] for x in config["devices"] if "_id" in x
                ]
            self.checked_out = {
                "ids": [station_id] + device_ids,
                "name": config.get("station", None),
            }
            self.checked_out.update(self.default_data)
            url = self.server_url + "/checkout"
            requests.post(url, json=self.checked_out, headers=self.headers)
            print("Notified boardfarm server of checkout")
            # Periodically let server know we're still using devices
            self.done_with_devices = multiprocessing.Event()
            w1 = multiprocessing.Process(target=self._poll,
                                         args=(self.done_with_devices, ))
            # daemon allows main program to exit anytime and kill this process
            w1.daemon = True
            w1.start()
            if self.debug:
                print(self.checked_out)
        except Exception as e:
            if self.debug:
                print(e)
                print("Failed to notify boardfarm server of checkout")

    def checkin(self):
        if not self.server_version or not self.checked_out:
            return
        try:
            # Stop polling
            self.done_with_devices.set()
            # and notify server
            url = self.server_url + "/checkin"
            requests.post(url, json=self.checked_out, headers=self.headers)
            print("Notified boardfarm server of checkin")
            if self.debug:
                print(self.checked_out)
        except Exception as e:
            if self.debug:
                print(e)
                print("Failed to notify boardfarm server of checkin")


if __name__ == "__main__":
    bf_config = "http://boardfarm.myexamplesite.com/api/bf_config"
    bfweb = BoardfarmWebClient(bf_config, debug=False)
    bfweb.checkout({
        "_id": "1111",
        "station": "rpi3",
        "devices": [{
            "_id": "1112"
        }]
    })
    time.sleep(65)
    bfweb.checkin()
