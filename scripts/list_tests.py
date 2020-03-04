#!/usr/bin/env python
import argparse
import re

from boardfarm import testsuites


def get_num(name):
    '''
    If a test case name contains a number, just return the number.
    Useful for sorting.
    '''
    result = re.search(r'\d+', name)
    if result:
        return int(result.group(0))
    else:
        return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Display test names in testsuite')
    parser.add_argument('testsuite', type=str, help='name of a test suite')
    args = parser.parse_args()
    names = testsuites.list_tests[args.testsuite]
    print("\n".join(sorted(names, key=get_num)))
