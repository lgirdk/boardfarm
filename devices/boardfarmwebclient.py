# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
#!/usr/bin/env python

import os
import re
import socket

import requests
from simplejson.errors import JSONDecodeError

class BoardfarmWebClient(object):
    '''
    Handles interacting with a boardfarm server. For checking out
    stations, etc.
    '''

    def __init__(self, config_url):
        self.config_url = config_url
        self.server_url = None
        self.server_version = None
        self.default_data = {'hostname': socket.gethostname(),
                             'username': os.environ.get('BUILD_USER_ID', None) or \
                                         os.environ.get('USER', None)
                            }
        # Test if this is a smart boardfarm server
        try:
            self.server_url = re.search('http.*/api', self.config_url).group(0)
            r = requests.get(self.server_url)
            data = r.json()
            self.server_version = data.get('version', None)
            print("Using %s as boardfarm server, version %s" % (self.server_url, self.server_version))
        except JSONDecodeError:
            print("Error: %s does not contain valid JSON." % self.config_url)
            raise
        except Exception as e:
            print("Using '%s' like a plain config file." % self.config_url)

    def checkout(self, name):
        if not self.server_version:
            return
        try:
            url = self.server_url + "/checkout"
            info = {"name": name}
            info.update(self.default_data)
            requests.post(url, json=info)
            print("Notified boardfarm server of checkout of %s" % name)
        except Exception as e:
            print(e)
            print("Failed to notify boardfarm server of checkout")

    def checkin(self, name):
        if not self.server_version:
            return
        try:
            url = self.server_url + "/checkin"
            info = {"name": name}
            info.update(self.default_data)
            requests.post(url, json=info)
            print("Notified boardfarm server of checkin of %s" % name)
        except Exception as e:
            print(e)
            print("Failed to notify boardfarm server of checkin")

if __name__ == '__main__':
    bf_config = "http://boardfarm.myexamplesite.com/api/bf_config"
    bfweb = BoardfarmWebClient(bf_config)
    bfweb.checkout("mv1-1-1")
    bfweb.checkin("mv1-1-1")
