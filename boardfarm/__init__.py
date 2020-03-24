# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import uuid
uniqid = uuid.uuid4().hex[:15]  # Random, unique ID and use first 15 bytes

from .version import __version__

from .Boardfarm import Boardfarm
from .plugins import find_plugins

plugins = find_plugins()

selftest_testsuite = "selftest"
