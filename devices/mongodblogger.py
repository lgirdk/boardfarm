# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
#!/usr/bin/env python

import datetime
import json
import os
import socket
import sys

import ipaddress
import pymongo

class ComplexEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ipaddress.IPv4Network) or \
           isinstance(obj, ipaddress.IPv4Address):
            return str(obj)
        elif isinstance(obj, datetime.datetime):
            return str(obj)
        else:
            try:
                return json.JSONEncoder.default(self, obj)
            except:
                print("WARNING: mongodblogger ComplexEncoder can't handle type %s" % type(obj))
                return ""

def pprint(x):
    '''Pretty print an object'''
    print(json.dumps(x, sort_keys=True, indent=2, cls=ComplexEncoder))

class MongodbLogger(object):
    '''
    Write data directly to mongodb.
    '''

    def __init__(self, host, username, password,
                 db_name='boardfarm',
                 collection_name='bft_run'):
        self.host = host
        self.username = username
        self.password = password
        self.db_name = db_name
        self.collection_name = collection_name
        # Connect to host
        connect_str = "mongodb+srv://%s:%s@%s/test?retryWrites=true&w=majority" % (self.username, self.password, self.host)
        self.client = pymongo.MongoClient(connect_str)
        self.db = self.client[self.db_name]
        self.collection = self.db[self.collection_name]
        # Set default data
        username = os.environ.get('BUILD_USER_ID', None)
        if username is None:
            username = os.environ.get('USER', '')
        self.default_data = {
            'hostname': socket.gethostname(),
            'user': username,
            'build_url': os.environ.get('BUILD_URL', 'None'),
            'change_list': os.environ.get('change_list', 'None'),
            'apss': os.environ.get('apss', 'None').split('-')[0],
            'manifest': os.environ.get('manifest', 'None'),
        }

    def log(self, data, debug=False):
        # Put in default data
        self.default_data['timestamp'] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        data.update(self.default_data)
        # Handle object types that json normally can't (converts them to a string or number)
        data = json.loads(json.dumps(data, cls=ComplexEncoder))
        if debug:
            print("Storing into mongodb:")
            pprint(data)
        post_id = self.collection.insert_one(data).inserted_id
        doc_url = "%s; db: %s; collection: %s; _id: %s" % (self.host, self.db_name, self.collection_name, post_id)
        print("Mongodb: Data stored at %s" % (doc_url))
