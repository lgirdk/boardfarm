# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import re

# no repr
newline = r"\r\n\[[^\]]+\]"
newline_match = r"\r\n\[([^\]]+)\]"
# with repr
newline_re = r"\\r\\n\[[^\]]+\]"
newline_re_match = r"\\r\\n\[([^\]]+)\]"

def prepare_log(log):
    '''Strips some stuff from outside logs so we can parse'''
    # TODO: convert other timestamps into seconds since boot
    return log

def split_results(results):
    t = [x[0] for x in results]
    r = [x[1] for x in results]

    if len(r) == len(t):
        return t, r

    # fallback to no timestamps
    return None, results

class Analysis():
    '''Base analysis class, each child class should implement the analyze function'''
    def analyze(self, console_log, output_dir):
        pass

    def make_graph(self, data, ylabel, fname, ts=None, xlabel="seconds", output_dir=None):
        '''Helper function to make a PNG graph'''
        if not output_dir:
            return

        # strings -> float for graphing
        ts = [float(i) for i in ts]
        try:
            data = [float(i) for i in data]
        except:
            data = [int(i) for i in data]

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        if ts is None:
            plt.plot(data)
        else:
            plt.plot(ts, data, marker='o')
        plt.ylabel(ylabel)
        plt.xlabel(xlabel)
        plt.gcf().set_size_inches(12, 8)
        plt.savefig(os.path.join(output_dir, "%s.png" % fname))
        plt.clf()

        # TODO: save simple CSV file?
