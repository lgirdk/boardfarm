# !/usr/bin/env python
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import datetime
import json
import os
import socket
import sys
from math import isnan

try:
    import elasticsearch
    from elasticsearch import RequestError
    from elasticsearch.serializer import JSONSerializer
except Exception as e:
    print(e)
    print("Please install needed module:\n" "  sudo pip install -U elasticsearch")
    sys.exit(1)


class Serializer(JSONSerializer):
    def default(self, obj):
        try:
            return JSONSerializer.default(self, obj)
        except TypeError:
            return str(obj)
        except Exception as error:
            print(error)
            return "Unable to serialize"


def pprint(x):
    """Pretty print an object."""
    print(json.dumps(x, sort_keys=True, indent=2))


class ElasticsearchLogger:
    """Write data directly to an elasticsearch cluster."""

    def __init__(self, server, index="boardfarm", doc_type="bft_run"):
        """Instance initialisation."""
        self.server = server
        self.index = index + "-" + datetime.datetime.utcnow().strftime("%Y.%m.%d")
        self.doc_type = doc_type
        # Connect to server
        self.es = elasticsearch.Elasticsearch([server], serializer=Serializer())
        # Set default data
        username = os.environ.get("BUILD_USER_ID", None)
        if username is None:
            username = os.environ.get("USER", "")
        self.default_data = {
            "hostname": socket.gethostname(),
            "user": username,
            "build_url": os.environ.get("BUILD_URL", "None"),
            "change_list": os.environ.get("change_list", "None"),
            "manifest": os.environ.get("manifest", "None"),
        }

    def log(self, data, debug=False):
        """Log data for elastic search."""
        # Put in default data
        self.default_data["@timestamp"] = datetime.datetime.utcnow().strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        data.update(self.default_data)

        data = {
            k: data[k] for k in data if not (type(data[k]) is float and isnan(data[k]))
        }

        if debug:
            print("Logging this data to Elastic:")
            pprint(data)

        try:
            result = self.es.index(index=self.index, doc_type=self.doc_type, body=data)
        except RequestError as e:
            print("Elastic logging error:")
            print(e.info)
            raise

        if result and "result" in result and result["result"] == "created":
            doc_url = f"{self.server}{self.index}/{self.doc_type}/{result['_id']}"
            print(f"Elasticsearch: Data stored at {doc_url}")
        else:
            print(result)
            raise Exception("Elasticsearch: problem storing data.")
        if debug:
            print(data)
