# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from datetime import datetime

start = datetime.now()

import uuid
uniqid = uuid.uuid4().hex[:15]  # Random, unique ID and use first 15 bytes

# TODO: remove wan/lan reference and just leave unique here
env = {"wan_iface": "wan%s" % uniqid[:12],
        "lan_iface": "lan%s" % uniqid[:12],
        "uniq_id": uniqid}

from .version import __version__

from .Boardfarm import Boardfarm
from .plugins import find_plugins

plugins = find_plugins()


