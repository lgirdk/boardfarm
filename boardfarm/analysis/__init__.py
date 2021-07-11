"""Import all analysis classes."""
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import glob
import importlib
import inspect
import logging
import os
import traceback

logger = logging.getLogger("bft")

# import all analysis classes
classes = {}
analysis_files = glob.glob(os.path.dirname(__file__) + "/*.py")
for x in sorted([os.path.basename(f)[:-3] for f in analysis_files if "__" not in f]):
    try:
        module = importlib.import_module(f"boardfarm.analysis.{x}")
    except Exception:
        traceback.print_exc()
        logger.error(f"Warning: could not import from file {x}.py")
        continue
    for thing_name in dir(module):
        thing = getattr(module, thing_name)
        if inspect.isclass(thing) and hasattr(thing, "analyze"):
            classes[thing_name] = thing
