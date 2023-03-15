"""Automated testing of network devices"""
__version__ = "2023.11.0"

import uuid

from .Boardfarm import Boardfarm  # noqa: F401
from .plugins import find_plugins, walk_library  # noqa: F401

uniqid = uuid.uuid4().hex[:15]  # Random, unique ID and use first 15 bytes

plugins = find_plugins()

selftest_testsuite = "selftest"
