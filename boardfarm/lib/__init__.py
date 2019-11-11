# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import glob
import os

import unittest2

from .ConfigHelper import ConfigHelper


def expectedFailureIf(test):
    def wrap(func):
        def wrapped(self, *args, **kwargs):
            if test():
                @unittest2.expectedFailure
                def f(): func(self)

                return f()
            return func(self)
        return wrapped
    return wrap

def find_subdirs(directories, name):
    '''
    Given a list of directories, find subdirectories with the given name.
    This is useful for finding devices and tests in boardfarm overlays.

    Note: This will only look in the base dir and then one subdirectory deep.
    '''
    result = []
    for d in directories:
        tmp = glob.glob(os.path.join(d, name)) + \
              glob.glob(os.path.join(d, '*', name))
        result += [os.path.join(d, x) for x in tmp]
        if len(tmp) > 1:
            # By design there shouldn't be more than one "devices" or "tests" directory in
            # a given boardfarm project
            print("WARNING: Multiple directories of the name %s found in %s." % (name, d))
            print("All will be used to find python classes")
    return result
