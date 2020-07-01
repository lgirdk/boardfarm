# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import uuid

from .Boardfarm import Boardfarm  # noqa: F401
from .plugins import find_plugins, walk_library
from .version import __version__  # noqa: F401

uniqid = uuid.uuid4().hex[:15]  # Random, unique ID and use first 15 bytes

plugins = find_plugins()

selftest_testsuite = "selftest"
