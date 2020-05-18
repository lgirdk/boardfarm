#!/usr/bin/env python

# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
"""module: arguments: bft's command-line options."""
import argparse
import inspect
import os
import os.path
import sys
import traceback

import boardfarm.lib.test_configurator
from boardfarm import config
from boardfarm.exceptions import TestImportError
from boardfarm.lib.common import check_url

try:
    import boardfarm
except ImportError:
    print("Please install boardfarm with the command:")
    cmd = "pip install -e ."
    if not os.path.isfile("setup.py"):
        tmp = os.path.abspath(
            os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         os.pardir))
        cmd = "cd %s ; %s" % (tmp, cmd)
    print(cmd)
    sys.exit(1)

HELP_EPILOG = """
Example use:

 bft -b ap148 --testsuite flash_only -m http://10.0.0.101/nand-ipq806x-single.img

 bft -b ap135 --testsuite preflight -r http://10.0.0.101/openwrt-ar71xx-generic-ap135-rootfs-squashfs.bin
"""


def parse():
    """Read command-line arguments, parse and store all values in boardfarm_config.

    Config can be fetched locally or remotely using HTTP.
    After parsing the config, devices from generic locations are moved inside selected
    boards.
    This method also initializes parameters for tests.

    :raises exception: Unable to access/read boardfarm configuration
    :return: boardfarm config module containing boardfarm_config
    :rtype: module
    """
    parser = argparse.ArgumentParser(
        description=
        "Connect to an available board, flash image(s), and run tests.",
        usage="bft [options...]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_EPILOG,
    )
    parser.add_argument(
        "-a",
        "--analysis",
        metavar="",
        type=str,
        default=None,
        help="Only run post processing analysis on logs",
    )
    parser.add_argument(
        "-b",
        "--board_type",
        metavar="",
        type=str,
        nargs="+",
        default=None,
        help="MODEL(s) of board to connect to",
    )
    parser.add_argument(
        "-c",
        "--config_file",
        metavar="",
        type=str,
        default=None,
        help="JSON config file for boardfarm",
    )
    parser.add_argument(
        "-e",
        "--extend",
        metavar="",
        type=str,
        default=None,
        action="append",
        help="NAME of extra test to run",
    )
    parser.add_argument(
        "-f",
        "--filter",
        metavar="",
        type=str,
        default=None,
        action="append",
        help="Regex filter off arbitrary board parameters",
    )
    parser.add_argument(
        "-g",
        "--golden",
        metavar="",
        type=str,
        default=[],
        nargs="+",
        help="Path to JSON results to compare against (golden master)",
    )
    parser.add_argument("-i",
                        "--inventory",
                        action="store_true",
                        help="List available boards and exit")
    parser.add_argument(
        "-k",
        "--kernel",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH of Kernel image to flash",
    )
    parser.add_argument("-l",
                        "--list_tests",
                        action="store_true",
                        help="List available tests and exit")
    parser.add_argument(
        "-m",
        "--meta_img_loc",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH to meta image to flash",
    )
    parser.add_argument(
        "-n",
        "--board_names",
        metavar="",
        type=str,
        nargs="+",
        default=[],
        help="NAME(s) of boards to run on",
    )
    owrt_tests_dir = os.path.join(os.getcwd(), "results", "")
    parser.add_argument(
        "-o",
        "--output_dir",
        metavar="",
        type=str,
        default=owrt_tests_dir,
        help="Directory to output results files too",
    )
    parser.add_argument(
        "-p",
        "--package",
        metavar="",
        type=str,
        action="append",
        default=None,
        help="URL or file PATH of ipk install after boot",
    )
    parser.add_argument(
        "-q",
        "--feature",
        metavar="",
        type=str,
        default=[],
        nargs="+",
        help="Features required for this test run",
    )
    parser.add_argument(
        "-r",
        "--rootfs",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH of Rootfs image to flash",
    )
    parser.add_argument(
        "-s",
        "--sysupgrade",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH to Sysupgrade image",
    )
    parser.add_argument(
        "-t",
        "--retry",
        type=int,
        default=0,
        help="How many times to retry every test if it fails",
    )
    parser.add_argument("-u",
                        "--uboot",
                        metavar="",
                        type=str,
                        default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument(
        "-w",
        "--wan",
        metavar="",
        type=str,
        default="dhcp",
        help="WAN protocol, dhcp (default) or pppoe",
    )
    parser.add_argument(
        "-x",
        "--testsuite",
        metavar="",
        type=str,
        default=None,
        help="NAME of test suite to run",
    )
    parser.add_argument(
        "-y",
        "--batch",
        action="store_true",
        help="Run in unattended mode - do not spawn console on failed test",
    )
    parser.add_argument(
        "-z",
        "--no-network",
        action="store_true",
        help="Skip basic network tests when booting",
    )
    parser.add_argument(
        "--bootargs",
        metavar="",
        type=str,
        default=None,
        help="bootargs to set or append to default args (board dependant)",
    )
    parser.add_argument(
        "--nfsroot",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH of Rootfs image to flash",
    )
    parser.add_argument("--version",
                        action="store_true",
                        help="show version and exit")
    parser.add_argument(
        "--nostrict",
        action="store_true",
        help="ignores failure to import a tests from a testsuite",
    )
    parser.add_argument(
        "--regex_config",
        metavar="",
        type=str,
        default=[],
        action="append",
        help="Regex substitution for board config",
    )
    parser.add_argument(
        "--err_dict",
        metavar="",
        type=str,
        default=[],
        nargs="+",
        help="Path to JSON containing the error injection dictionary",
    )
    parser.add_argument(
        "--arm",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH of Arm software image to flash.",
    )
    parser.add_argument(
        "--atom",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH of Atom software image to flash.",
    )
    parser.add_argument(
        "--combined",
        metavar="",
        type=str,
        default=None,
        help="URL or file PATH of ARM&ATOM Combined software image to flash.",
    )

    args = parser.parse_args()

    if args.version:
        print("%s %s" % (os.path.basename(sys.argv[0]), boardfarm.__version__))
        if boardfarm.plugins:
            print("Installed Plugins:")
            for key in sorted(boardfarm.plugins):
                print(
                    "%s %s" %
                    (key, getattr(boardfarm.plugins[key], "__version__", "")))
            print("Python: %s" % sys.version)
        sys.exit(0)

    if args.list_tests:
        try:
            from boardfarm import tests

            tests.init(config)
        except TestImportError as e:
            print(e)
            sys.exit(1)
        for k, v in sorted(tests.available_tests.items()):
            try:
                print("%20s - %s" % (k, v.__doc__.split("\n")[0]))
            except Exception as error:
                print(error)
                print("%20s -" % k)
        sys.exit(0)

    try:
        if args.config_file is not None:
            config.boardfarm_config_location = args.config_file
        (
            config.boardfarm_config_location,
            config.boardfarm_config,
        ) = boardfarm.lib.test_configurator.get_station_config(
            config.boardfarm_config_location, bool(args.config_file))
    except Exception as e:
        print(e)
        print("Unable to access/read boardfarm configuration from %s" %
              config.boardfarm_config_location)
        sys.exit(1)

    # Check if boardfarm configuration is empty
    if not config.boardfarm_config:
        print("ERROR! Boardfarm config at %s is empty, so" % args.config_file)
        print("either all stations are in use or disabled.")
        sys.exit(10)
    # Check if given board type(s) have any overlap with available board types from config
    if args.board_type:
        all_board_types = []
        for key in config.boardfarm_config:
            elem = (config.boardfarm_config[key].get("board_type", None)
                    if type(config.boardfarm_config[key]) is dict else None)
            if elem:
                all_board_types.append(elem)

        if not (set(args.board_type) & set(all_board_types)):
            print("ERROR! You specified board types: %s " %
                  " ".join(args.board_type))
            print("but that is not an existing & available type of board.")
            print("Please choose a board type from:")
            print("\n".join([" * %s" % x for x in set(all_board_types)]))
            sys.exit(10)
    # Check if given board name(s) are present in available boards
    if args.board_names:
        all_board_names = [
            key for key in config.boardfarm_config if key != "locations"
        ]
        if not (set(args.board_names) & set(all_board_names)):
            print("ERROR! You specified board names: %s " %
                  " ".join(args.board_names))
            print("but that is not an existing & available board.")
            print("Please choose a board name from:")
            print("\n".join([" * %s" % x for x in sorted(all_board_names)]))
            sys.exit(10)

    config.batch = args.batch

    if args.inventory:
        print("%11s  %15s  %5s  %25s  %25s  %s" %
              ("Name", "Model", "Auto", "LAN", "WAN", "Notes"))
        bf = config.boardfarm_config
        for i, b in enumerate(sorted(bf)):
            if args.board_type is None or bf[b].get(
                    "board_type") in args.board_type:
                if not args.board_names or b in args.board_names:
                    info = {
                        "name": b,
                        "type": bf[b].get("board_type"),
                        "wlan": bf[b].get("wlan_device") is not None,
                        "auto": bf[b].get("available_for_autotests", True),
                        "conn_cmd": bf[b].get("conn_cmd"),
                        "lan_device": bf[b].get("lan_device", ""),
                        "wan_device": bf[b].get("wan_device", ""),
                        "notes": bf[b].get("notes", ""),
                    }
                    if not args.filter or (
                            args.filter
                            and boardfarm.lib.test_configurator.filter_boards(
                                bf[b], args.filter)):
                        print(
                            "%(name)11s  %(type)15s  %(auto)5s  %(lan_device)25s  %(wan_device)25s  %(notes)s"
                            % info)
        print("To connect to a board by name:\n  ./bft -x connect -n NAME")
        print(
            "To connect to any board of a given model:\n  ./bft -x connect -b MODEL"
        )
        sys.exit(0)

    if hasattr(config, "INSTALL_PKGS") is False:
        config.INSTALL_PKGS = ""

    config.retry = args.retry

    if args.package:
        for pkg in args.package:
            config.INSTALL_PKGS += " %s" % pkg

    config.UBOOT = args.uboot
    config.KERNEL = args.kernel
    config.ROOTFS = args.rootfs
    config.ARM = args.arm
    config.ATOM = args.atom
    config.COMBINED = args.combined
    config.NFSROOT = args.nfsroot
    config.META_BUILD = args.meta_img_loc
    # Quick check to make sure file url/path arguments are reasonable
    for x in (
            config.UBOOT,
            config.KERNEL,
            config.ROOTFS,
            config.META_BUILD,
            config.ARM,
            config.ATOM,
            config.COMBINED,
    ):
        if x is None:
            continue
        if "mirror://" in x:
            # we need to check the mirror later once the board is selected
            continue
        if x.startswith("http://") or x.startswith("https://"):
            if not check_url(x):
                sys.exit(1)
        else:
            if not os.path.isfile(x):
                print("File not found: %s" % x)
                sys.exit(1)

    if args.sysupgrade:
        config.SYSUPGRADE_NEW = args.sysupgrade
    if args.testsuite:
        config.TEST_SUITE = args.testsuite
    else:
        if args.extend:
            # One or more test cases was specified at command-line, just boot first.
            config.TEST_SUITE = "flash"
        else:
            # No test suite or test cases specified, so just boot and interact.
            config.TEST_SUITE = "interact"
    if args.extend:
        config.EXTRA_TESTS = args.extend
        config.EXTRA_TESTS += ["Interact"]

    config.output_dir = os.path.abspath(args.output_dir) + os.sep
    try:
        os.mkdir(config.output_dir)
    except Exception as error:
        print(error)
        pass

    if args.analysis:
        from boardfarm import analysis

        for cstr in dir(analysis):
            c = getattr(analysis, cstr)
            if inspect.isclass(c) and issubclass(c, analysis.Analysis):
                sys.stdout.write("Running analysis class = %s... " % c)
                console_log = open(args.analysis, "r").read()
                from boardfarm.analysis.analysis import prepare_log

                try:
                    c().analyze(prepare_log(console_log), config.output_dir)
                    print("DONE!")
                except Exception:
                    print("FAILED!")
                    traceback.print_exc(file=sys.stdout)
                    continue
        exit(0)

    config.BOARD_NAMES = boardfarm.lib.test_configurator.filter_station_config(
        config.boardfarm_config,
        board_type=args.board_type,
        board_names=args.board_names,
        board_features=args.feature,
        board_filter=args.filter,
    )
    if args.board_type:
        if not config.BOARD_NAMES:
            print(
                "ERROR! No boards meet selection requirements and have available_for_autotests = True."
            )
            sys.exit(10)
    else:
        if not args.board_names:
            print("ERROR")
            print("You must specify a board name with the '-n' argument:")
            print("./run-all.py -n 3000")
            print(
                "That same board name must be present in boardfarm configuration."
            )
            sys.exit(1)

    if args.err_dict:
        config.update_error_injection_dict(args.err_dict)

    # grab golden master results
    if args.golden:
        config.golden = args.golden
    config.golden_master_results = {}
    if config.golden is not []:
        import requests

        for g in config.golden:
            try:
                config.golden_master_results.update(requests.get(g).json())
            except Exception as error:
                print(error)
                print("Failed to fetch golden master results from %s" % g)
                sys.exit(15)

    config.WAN_PROTO = args.wan
    config.setup_device_networking = not args.no_network
    config.bootargs = args.bootargs
    config.golden = args.golden
    config.features = args.feature
    config.TEST_SUITE_NOSTRICT = args.nostrict
    config.regex_config = args.regex_config

    return config


if __name__ == "__main__":
    configuration = parse()
    # Display configuration
    for key in sorted(dir(configuration)):
        if key.startswith("__"):
            continue
        print("%s: %s" % (key, getattr(configuration, key)))
