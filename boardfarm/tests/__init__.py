# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import glob
import importlib
import inspect
import os
import traceback

import boardfarm
from boardfarm.exceptions import TestImportError

available_tests = {}


def init(config=None):
    """Dynamically find all test classes accross all boardfarm projects.

    This creates a dictionary of "test names" to "python object of test class".
    """
    # This will be a dictionary where:
    #   key = filename (without '.py')
    # value = list of classes
    test_mappings = {}

    # Create a dictionary of all boardfarm modules
    all_boardfarm_modules = dict(
        boardfarm.plugins
    )  # use dict() to create a copy instead of a reference
    all_boardfarm_modules["boardfarm"] = importlib.import_module("boardfarm")

    # Loop over all modules to import their tests
    for modname in all_boardfarm_modules:
        # Find all python files in 'tests' directories
        location = os.path.join(
            os.path.dirname(all_boardfarm_modules[modname].__file__), "tests")
        file_names = glob.glob(os.path.join(location, "*.py"))
        file_names = [
            os.path.basename(x)[:-3] for x in file_names if "__" not in x
        ]
        for fname in sorted(file_names):
            tmp = "%s.tests.%s" % (modname, fname)
            try:
                module = importlib.import_module(tmp)
            except Exception:
                traceback.print_exc()
                raise TestImportError(
                    "Error: Could not import from test file %s.py" % fname)
            if fname in test_mappings:
                print("WARNING: Two test files have the same name, %s.py" %
                      fname)
            test_mappings[fname] = []
            for thing_name in dir(module):
                thing = getattr(module, thing_name)
                if inspect.isclass(thing) and hasattr(thing, "run"):
                    test_mappings[fname].append(thing)

    # Loop over all test classes in all test files, and
    # run their 'parse' function if they have one.
    for test_file, tests in test_mappings.items():
        for test in tests:
            if not hasattr(test, "parse"):
                continue
            try:
                if config is not None:
                    new_tests = test.parse(config) or []
                    for new_test in new_tests:
                        available_tests[new_test.__name__] = new_test
            except Exception:
                if "BFT_DEBUG" in os.environ:
                    traceback.print_exc()
                print("Warning: Failed to run parse function in %s" %
                      inspect.getsourcefile(test))

    # Build dictionary where
    #   key = test name
    #   value = reference to test class
    for key in test_mappings:
        for item in test_mappings[key]:
            available_tests[item.__name__] = item
