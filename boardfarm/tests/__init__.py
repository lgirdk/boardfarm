# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import glob
import inspect
import sys
import traceback

from boardfarm.lib import find_subdirs

available_tests = {}

def init(config):
    test_files = glob.glob(os.path.dirname(__file__) + "/*.py")
    boardfarm_overlays = os.environ.get('BFT_OVERLAY')
    if boardfarm_overlays:
        # Insert 'tests' directories from the overlays
        dirs = boardfarm_overlays.split(" ")
        for x in find_subdirs(dirs, "tests"):
            sys.path.insert(0, x)
            test_files += glob.glob(os.path.join(x, '*.py'))

    test_mappings = {}
    for x in sorted([os.path.basename(f)[:-3] for f in test_files if not "__" in f]):
        if x == "tests":
            raise Exception("INVALID test file name found, tests.py will cause namespace issues, please rename")
        try:
            test_file = None
            exec("import %s as test_file" % x)
            assert test_file is not None
            test_mappings[test_file] = []
            for obj in dir(test_file):
                ref = getattr(test_file, obj)
                if inspect.isclass(ref) and hasattr(ref, 'run'):
                    test_mappings[test_file].append(ref)
                    exec("from %s import %s" % (x, obj))
        except Exception as e:
            if 'BFT_DEBUG' in os.environ:
                traceback.print_exc()
                print("Warning: could not import from file %s.py" % x)
            else:
                print("Warning: could not import from file %s.py. Run with BFT_DEBUG=y for more details" % x)

    for test_file, tests in test_mappings.iteritems():
        for test in tests:
            if not hasattr(test, "parse"):
                continue
            try:
                new_tests = test.parse(config) or []
                for new_test in new_tests:
                    available_tests[new_test] = getattr(test_file, new_test)
            except Exception:
                if 'BFT_DEBUG' in os.environ:
                    traceback.print_exc()
                print("Warning: Failed to run parse function in %s" % inspect.getsourcefile(test))

    # Build dictionary where
    #   key = test name
    #   value = reference to test class
    for key in test_mappings:
        for item in test_mappings[key]:
            available_tests[item.__name__] = item


