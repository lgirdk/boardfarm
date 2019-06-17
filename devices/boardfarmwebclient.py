# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
#!/usr/bin/env python

import re

import requests


class BoardfarmWebClient(object):
    '''
    Handles interacting with a boardfarm server. For checking out
    stations, etc.
    '''

    def __init__(self, config_url):
        self.config_url = config_url
        self.server_url = None
        self.server_version = None
        # Test if this is a smart boardfarm server
        try:
            self.server_url = re.search('http.*/api', self.config_url).group(0)
            r = requests.get(self.server_url)
            data = r.json()
            self.server_version = data.get('version', None)
        except:
            print("%s does not appear to be a boardfarm server" % self.config_url)

    def checkout(self, name):
        url = self.server_url + "/checkout"
        if not self.server_version:
            return
        try:
            requests.post(url, json={"name": name})
            print("Notified boardfarm server of checkout of %s" % name)
        except Exception as e:
            print(e)
            print("Failed to notify server of checkout")

    def checkin(self, name):
        url = self.server_url + "/checkin"
        if not self.server_version:
            return
        try:
            requests.post(url, json={"name": name})
            print("Notified boardfarm server of checkin of %s" % name)
        except Exception as e:
            print(e)
            print("Failed to notify server of checkin")

if __name__ == '__main__':
    bf_config = "http://boardfarm.myexamplesite.com/api/bf_config"
    bfweb = BoardfarmWebClient(bf_config)
    bfweb.checkout("mv1-1-1")
    bfweb.checkin("mv1-1-1")
