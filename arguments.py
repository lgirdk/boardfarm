#!/usr/bin/env python

# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import argparse
import inspect
import os
import os.path
import sys
import json
import unittest2
try:
    from urllib.request import urlopen
    import urllib
except:
    from urllib2 import urlopen
    import urllib2 as urllib
import re

import library
import config
from config import boardfarm_config_location

def filter_boards(board_config, filter, name=None):
    s = ""
    for k, v in board_config.items():
        s += "%s : %s\n" % (k, v)

    if all(re.findall(f, s) for f in filter):
        if name:
            print("matched %s on %s, adding %s" % (filter, board_config, name))
        return True
    return False

HELP_EPILOG = '''
Example use:

 bft -b ap148 --testsuite flash_only -m http://10.0.0.101/nand-ipq806x-single.img

 bft -b ap135 --testsuite preflight -r http://10.0.0.101/openwrt-ar71xx-generic-ap135-rootfs-squashfs.bin
'''

def parse():
    '''
    Read command-line arguments, return a simple configuration for running tests.
    '''
    parser = argparse.ArgumentParser(description='Connect to an available board, flash image(s), and run tests.',
                                     usage='bft [options...]',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=HELP_EPILOG)
    parser.add_argument('-l', '--list_tests', action='store_true', help='List available tests and exit')
    parser.add_argument('-i', '--inventory', action='store_true', help='List available boards and exit')
    parser.add_argument('-y', '--batch', action='store_true', help='Run in unattended mode - do not spawn console on failed test')
    parser.add_argument('-t', '--retry', type=int, default=0, help='How many times to retry every test if it fails')
    parser.add_argument('-k', '--kernel', metavar='', type=str, default=None, help='URL or file PATH of Kernel image to flash')
    parser.add_argument('-r', '--rootfs', metavar='', type=str, default=None, help='URL or file PATH of Rootfs image to flash')
    parser.add_argument('--nfsroot', metavar='', type=str, default=None, help='URL or file PATH of Rootfs image to flash')
    parser.add_argument('-m', '--meta_img_loc', metavar='', type=str, default=None, help='URL or file PATH to meta image to flash')
    parser.add_argument('-p', '--package', metavar='', type=str, action="append", default=None, help='URL or file PATH of ipk install after boot')
    parser.add_argument('-u', '--uboot', metavar='', type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument('-s', '--sysupgrade', metavar='', type=str, default=None, help='URL or file PATH to Sysupgrade image')
    parser.add_argument('-x', '--testsuite', metavar='', type=str, default=None, help='NAME of test suite to run')
    parser.add_argument('-e', '--extend', metavar='', type=str, default=None, action="append", help='NAME of extra test to run')
    parser.add_argument('-n', '--board_names', metavar='', type=str, nargs='+', default=[], help='NAME(s) of boards to run on')
    parser.add_argument('-b', '--board_type', metavar='', type=str, nargs='+', default=None, help='MODEL(s) of board to connect to')
    parser.add_argument('-w', '--wan', metavar='', type=str, default='dhcp', help='WAN protocol, dhcp (default) or pppoe')
    parser.add_argument('-v', '--reboot-vms', action="store_true", help='Reboot VMs before starting tests')
    parser.add_argument('-f', '--filter', metavar='', type=str, default=None, action="append", help='Regex filter off arbitrary board parameters')
    parser.add_argument('-a', '--analysis', metavar='', type=str, default=None, help='Only run post processing analysis on logs')
    owrt_tests_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "results", '')
    parser.add_argument('-o', '--output_dir', metavar='', type=str, default=owrt_tests_dir, help='Directory to output results files too')
    parser.add_argument('-z', '--no-network', action='store_true', help='Skip basic network tests when booting')
    parser.add_argument('-c', '--config_file', metavar='', type=str, default=boardfarm_config_location, help='JSON config file for boardfarm')
    parser.add_argument('--bootargs', metavar='', type=str, default=None, help='bootargs to set or append to default args (board dependant)')
    parser.add_argument('-g', '--golden', metavar='', type=str, default=[], nargs='+', help='Path to JSON results to compare against (golden master)')
    parser.add_argument('-q', '--feature', metavar='', type=str, default=[], nargs='+', help='Features required for this test run')

    args = parser.parse_args()

    if args.list_tests:
        import tests
        tests.init(config)
        # Print all classes that are a subclass of TestCase
        for e in dir(tests):
            thing = getattr(tests, e)
            if inspect.isclass(thing) and \
               issubclass(thing, unittest2.TestCase):
                try:
                    print("%20s - %s" % (e, thing.__doc__.split('\n')[0]))
                except:
                    print("%20s -" % e)
        sys.exit(0)

    try:
        if args.config_file.startswith("http"):
            data = urlopen(args.config_file).read().decode()
        else:
            data = open(args.config_file, 'r').read()
        config.boardfarm_config = json.loads(data)

        if 'locations' in config.boardfarm_config:
            location = config.boardfarm_config['locations']
            del config.boardfarm_config['locations']

            for board in config.boardfarm_config:
                if 'location' in config.boardfarm_config[board]:
                    board_location = config.boardfarm_config[board]['location']
                    if board_location in location:
                        for key, value in location[board_location].iteritems():
                            if type(value) == list:
                                config.boardfarm_config[board][key].extend(value)
                            else:
                                config.boardfarm_config[board][key] = value

    except Exception as e:
        print(e)
        print('Unable to access/read Board Farm configuration\n%s' % boardfarm_config_location)
        sys.exit(1)

    config.batch = args.batch

    if args.inventory:
        print("%11s  %15s  %5s  %25s  %25s  %s" % ('Name', 'Model', 'Auto', 'LAN', 'WAN', 'Notes'))
        bf = config.boardfarm_config
        for i, b in enumerate(sorted(bf)):
            if args.board_type is None or bf[b].get('board_type') in args.board_type:
                if not args.board_names or b in args.board_names:
                    info = {'name': b,
                            'type': bf[b].get('board_type'),
                            'wlan': bf[b].get('wlan_device') != None,
                            'auto': bf[b].get('available_for_autotests', True),
                            'conn_cmd': bf[b].get('conn_cmd'),
                            'lan_device': bf[b].get('lan_device', ''),
                            'wan_device': bf[b].get('wan_device', ''),
                            'notes': bf[b].get('notes', "")}
                    if not args.filter or (args.filter and filter_boards(bf[b], args.filter)):
                        print("%(name)11s  %(type)15s  %(auto)5s  %(lan_device)25s  %(wan_device)25s  %(notes)s" % info)
        print("To connect to a board by name:\n  ./bft -x connect -n NAME")
        print("To connect to any board of a given model:\n  ./bft -x connect -b MODEL")
        sys.exit(0)

    if hasattr(config, 'INSTALL_PKGS') is False:
        config.INSTALL_PKGS = ""

    config.retry = args.retry

    if args.package:
        for pkg in args.package:
            config.INSTALL_PKGS += " %s" % pkg

    config.UBOOT = args.uboot
    config.KERNEL = args.kernel
    config.ROOTFS = args.rootfs
    config.NFSROOT = args.nfsroot
    config.META_BUILD = args.meta_img_loc
    # Quick check to make sure file url/path arguments are reasonable
    for x in (config.UBOOT, config.KERNEL, config.ROOTFS, config.META_BUILD):
        if x is None:
            continue
        if x.startswith('http://') or x.startswith('https://'):
            try:
		def add_basic_auth(login_str, request):
		    '''Adds Basic auth to http request, pass in login:password as string'''
		    import base64
		    encodeuser = base64.b64encode(login_str.encode('utf-8')).decode("utf-8")
		    authheader =  "Basic %s" % encodeuser
		    request.add_header("Authorization", authheader)

                import ssl
                context = ssl._create_unverified_context()

		req = urllib.Request(x)

                try:
                    import netrc, urlparse
                    n = netrc.netrc()
                    login, unused, password = n.authenticators(urlparse.urlparse(x).hostname)
		    add_basic_auth("%s:%s" % (login, password), req)
                except (TypeError, ImportError, IOError, netrc.NetrcParseError):
                    pass

                # If url returns 404 or similar, raise exception
                urlopen(req, timeout=20, context=context)
            except Exception as e:
                print(e)
                print('Error trying to access %s' % x)
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
    except:
        pass

    if args.analysis:
        import analysis
        for cstr in dir(analysis):
            c = getattr(analysis, cstr)
            if inspect.isclass(c) and issubclass(c, analysis.Analysis):
                sys.stdout.write("Running analysis class = %s... " % c)
                console_log = open(args.analysis, 'r').read()
                from analysis.analysis import prepare_log
                try:
                    c().analyze(prepare_log(console_log), config.output_dir)
                    print("DONE!")
                except:
                    print("FAILED!")
                    continue
        exit(0)

    if args.board_type:
        library.print_bold("Selecting board from board type = %s" % args.board_type)
        config.BOARD_NAMES = []
        possible_names = config.boardfarm_config
        if args.board_names:
            print("Board names = %s" % args.board_names)
            # Allow selection only from given set of board names
            possible_names = set(config.boardfarm_config) & set(args.board_names)
        for b in possible_names:
            if len(args.board_names) != 1 and \
               'available_for_autotests' in config.boardfarm_config[b] and \
               config.boardfarm_config[b]['available_for_autotests'] == False:
                # Skip this board
                continue
            if args.feature != [] :
                if 'feature' not in config.boardfarm_config[b]:
                    continue
                features = config.boardfarm_config[b]['feature']
                if type(features) is str or type(features) is unicode:
                    features = [features]
                if set(args.feature) != set(args.feature) & set(features):
                    continue
            for t in args.board_type:
                if config.boardfarm_config[b]['board_type'].lower() == t.lower():
                    if args.filter:
                        if filter_boards(config.boardfarm_config[b], args.filter, b):
                            config.BOARD_NAMES.append(b)
                    else:
                        config.BOARD_NAMES.append(b)
        if not config.BOARD_NAMES:
            print("ERROR! No boards meet selection requirements and have available_for_autotests = True.")
            sys.exit(1)
    else:
        if not args.board_names:
            print("ERROR")
            print("You must specify a board name with the '-n' argument:")
            print("./run-all.py -n 3000")
            print("That same board name must be present in boardfarm configuration.")
            sys.exit(1)
        else:
            config.BOARD_NAMES = args.board_names


    config.WAN_PROTO = args.wan
    config.reboot_vms = args.reboot_vms
    config.setup_device_networking = not args.no_network
    config.bootargs = args.bootargs
    config.golden = args.golden
    config.features = args.feature

    return config

if __name__ == '__main__':
    config = parse()
    # Display configuration
    for key in sorted(dir(config)):
        if key.startswith('__'):
            continue
        print("%s: %s" % (key, getattr(config, key)))
