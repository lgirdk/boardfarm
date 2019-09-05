# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
from boardfarm import lib

# Import from every file
import os
import glob
import unittest2
import inspect
import sys

test_files = glob.glob(os.path.dirname(__file__) + "/*.py")
if 'BFT_OVERLAY' in os.environ:
    for overlay in os.environ['BFT_OVERLAY'].split(' '):
        overlay = os.path.abspath(overlay)
        sys.path.insert(0, overlay + '/tests')
        test_files += glob.glob(overlay + '/tests/*.py')

    sys.path.insert(0, os.getcwd() + '/tests')

test_mappings = {}
for x in sorted([os.path.basename(f)[:-3] for f in test_files if not "__" in f]):
    if x == "tests":
        raise Exception("INVALID test file name found, tests.py will cause namespace issues, please rename")
    try:
        exec("import %s as test_file" % x)
        test_mappings[test_file] = []
        for obj in dir(test_file):
            ref = getattr(test_file, obj)
            if inspect.isclass(ref) and issubclass(ref, unittest2.TestCase):
                test_mappings[test_file].append(ref)
                exec("from %s import %s" % (x, obj))
    except Exception as e:
        if 'BFT_DEBUG' in os.environ:
            import traceback
            traceback.print_exc()
            print("Warning: could not import from file %s.py" % x)
        else:
            print("Warning: could not import from file %s.py. Run with BFT_DEBUG=y for more details" % x)

def init(config):
    for test_file, tests in test_mappings.iteritems():
        for test in tests:
                #print('checking %s in %s' % (test, test_file))
            if hasattr(test, "parse"):
                try:
                    #print("calling parse on %s" % test)
                    new_tests = test.parse(config) or []
                    for new_test in new_tests:
                        globals()[new_test] = getattr(test_file, new_test)
                except Exception as e:
                    if 'BFT_DEBUG' in os.environ:
                        import traceback
                        traceback.print_exc()
                    print("Failed to run %s parse function!" % test)
                    pass
