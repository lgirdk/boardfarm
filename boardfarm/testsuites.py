# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.


# Read simple test suite config files
import config
import devices.configreader
tmp = devices.configreader.TestsuiteConfigReader()

config_files = config.testsuite_config_files
for ovrly_name, ovrly in config.layerconfs:
    if hasattr(ovrly, 'testsuite_config_files'):
        config_files += ovrly.testsuite_config_files

tmp.read(config_files)

list_tests = tmp.section

# Create long or complicated test suites at run time.
# key = suite name, value = list of tests names (strings)
new_tests = {}

# Combine simple and dynamic dictionary of test suites
list_tests.update(new_tests)
