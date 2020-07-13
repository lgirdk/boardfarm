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
import pkgutil
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

    all_mods = []

    # Loop over all modules to import their tests
    for modname in all_boardfarm_modules:
        bf_module = all_boardfarm_modules[modname]
        test_module = pkgutil.get_loader(".".join([bf_module.__name__, "tests"]))
        if test_module:
            all_mods += boardfarm.walk_library(
                test_module.load_module(), filter_pkgs=["lib"]
            )

    for module in all_mods:
        fname = module.__name__.split(".")[-1]
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
                print(
                    "Warning: Failed to run parse function in %s"
                    % inspect.getsourcefile(test)
                )

    # Build dictionary where
    #   key = test name
    #   value = reference to test class
    for key in test_mappings:
        for item in test_mappings[key]:
            available_tests[item.__name__] = item
