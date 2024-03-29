# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import glob
import logging
import os

from .ConfigHelper import ConfigHelper  # noqa: F401

logger = logging.getLogger("bft")


def find_subdirs(directories, name):
    """
    Given a list of directories, find subdirectories with the given name.

    This is useful for finding devices and tests in boardfarm overlays.

    Note: This will only look in the base dir and then one subdirectory deep.
    """
    result = []
    for d in directories:
        tmp = glob.glob(os.path.join(d, name)) + glob.glob(os.path.join(d, "*", name))
        result += [os.path.join(d, x) for x in tmp]
        if len(tmp) > 1:
            # By design there shouldn't be more than one "devices" or "tests" directory in
            # a given boardfarm project
            logger.error(
                f"WARNING: Multiple directories of the name {name} found in {d}."
            )
            logger.error("All will be used to find python classes")
    return result
