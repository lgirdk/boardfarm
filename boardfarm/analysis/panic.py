"""Parse logs for kernel panic events."""
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import re

from . import analysis


class PanicAnalysis(analysis.Analysis):
    """Parse logs for kernel panic events."""

    def analyze(self, console_log, output_dir):
        """Find kernel panic events from console logs."""
        if len(re.findall("Kernel panic", console_log)):
            print("ERROR: log had panic")
