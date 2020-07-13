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

# import all analysis classes
classes = {}
analysis_files = glob.glob(os.path.dirname(__file__) + "/*.py")
for x in sorted([os.path.basename(f)[:-3] for f in analysis_files if "__" not in f]):
    try:
        module = importlib.import_module("boardfarm.analysis.%s" % x)
    except Exception:
        if "BFT_DEBUG" in os.environ:
            traceback.print_exc()
            print("Warning: could not import from file %s.py" % x)
        else:
            print(
                "Warning: could not import from file %s.py. Run with BFT_DEBUG=y for more details"
                % x
            )
        continue
    for thing_name in dir(module):
        thing = getattr(module, thing_name)
        if inspect.isclass(thing) and hasattr(thing, "analyze"):
            classes[thing_name] = thing
