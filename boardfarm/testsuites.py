# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import glob
import os

import boardfarm
from boardfarm.dbclients import configreader
tmp = configreader.TestsuiteConfigReader()

# Build a list of all testsuite config files. Name should match "testsuites*.cfg"
config_files = []
for modname in sorted(boardfarm.plugins):
    overlay = os.path.dirname(boardfarm.plugins[modname].__file__)
    config_files += glob.glob(os.path.join(overlay, 'testsuites*.cfg'))

tmp.read(config_files)

list_tests = tmp.section

# Create long or complicated test suites at run time.
# key = suite name, value = list of tests names (strings)
new_tests = {}

# Combine simple and dynamic dictionary of test suites
list_tests.update(new_tests)
