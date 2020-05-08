# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import re

import termcolor


def print_bold(msg):
    termcolor.cprint(msg, None, attrs=['bold'])


# Add this to your env if you need to disable this for some reason
BFT_DISABLE_ERROR_DETECT = "BFT_DISABLE_ERROR_DETECT" in os.environ


def detect_kernel_panic(console, s):
    if re.findall("Kernel panic - not syncing", s):
        console.close()

        raise Exception('Kernel panic detected')


def detect_crashdump_error(console, s):
    if re.findall("Crashdump magic found", s):
        print_bold("Crashdump magic found, trying to save data...")

        console.sendcontrol('c')
        console.sendcontrol('c')
        console.sendcontrol('c')
        console.expect('<INTERRUPT>')
        console.expect(console.uprompt)
        console.setup_uboot_network()
        console.sendline("dumpipq_data")

        tftp_progress = "#" * 30
        tftp_start = "TFTP to server"
        tftp_done = "Bytes transferred"
        tftp_expect = [tftp_progress, tftp_start, tftp_done]

        i = -1
        try:
            # this waits until we get the reseting message which means
            # we are done
            while i < 3:
                i = console.expect(tftp_expect +
                                   ["Resetting with watch dog!"] +
                                   console.uprompt)
        except:
            print_bold("Crashdump upload failed")
        else:
            print_bold("Crashdump upload succeeded")

        # TODO: actually parse data too?
        raise Exception('Crashdump detected')


def detect_fatal_error(console):
    if BFT_DISABLE_ERROR_DETECT:
        return

    s = ""

    if isinstance(console.before, str):
        s += console.before
    if isinstance(console.after, str):
        s += console.after

    detect_crashdump_error(console, s)
