#!/usr/bin/env python

import argparse
import os
import re
import subprocess
import sys

def get_all_classes_from_code(directories, debug=False):
    '''
    Uses 'grep' to find all files of type '.py' in the given directories.
    Then parses those files to return a dict where:
         * keys = class names
         * values = parent class name
    '''
    if debug:
        print("Searching for classes in:")
    raw_text = []
    for d in directories:
        if debug:
            print(d)
        cmd = "grep -E '^class' %s" % d
        try:
            result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
            raw_text.append(result)
        except subprocess.CalledProcessError:
            if debug:
                print("Warning: No tests found in %s" % d)
    raw_text = "".join(raw_text)
    all_classes = dict(re.findall('class\s(\w+)\(([\w\.]+)\):', raw_text))
    if debug:
        print("Found %s python classes." % len(all_classes))
        #print("All classes and their parent found in code:")
        #print("\n".join(["%s -> %s" % (k,v) for k,v in sorted(all_classes.iteritems())]))
    return(all_classes)

def replace_parent_with_grandparent(data, no_modify, debug=False):
    '''
    Given a dictionary where all keys are class names, and values are parent classes,
    return a dictionary with parent class names replaced with grandparent class names.
    '''
    new_dict = {}
    for key in data:
        if data[key] in no_modify:
            new_dict[key] = data[key]
            continue
        new_dict[key] = data.get(data[key], data[key])
    return new_dict

def changed_classes(directories, start, end, debug=False):
    '''
    Return names of all changed classes in a "git diff".
    '''
    if debug:
        print("\nSearching for differences:")
    result = {}
    for d in directories:
        try:
            cmd = "git --git-dir %s diff %s..%s -U0" % (d, start, end)
            if debug:
                print(cmd)
            diff = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
            result.update(dict(re.findall('class\s(\w+)\(([\w\.]+)\):', diff)))
        except subprocess.CalledProcessError:
            if debug:
                print("Warning: git diff command failed in %s" % d)
    if debug:
        print("\nAll changed classes from %s to %s:" % (start, end))
        print("  " + "\n  ".join(result.keys()))
    return result

def get_features(directories, start, end, debug=False):
    '''
    Return the list of words after 'Features:' in git log messages.
    '''
    if debug:
        print("\nSearching for 'Features' in git log:")
    result = []
    for d in directories:
        try:
            cmd = "git --git-dir %s log %s..%s" % (d, start, end)
            if debug:
                print(cmd)
            text = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
            result += re.findall('Features:\s(\w+)', text)
        except subprocess.CalledProcessError:
            if debug:
                print("Warning: git log command failed in %s" % d)
    if debug:
        print("\nFeatures requested in git log from %s to %s:" % (start, end))
        print(" ".join(set(result)))
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prosses a "git diff" to find test changes.')
    parser.add_argument('start', type=str, help='Begining git hash')
    parser.add_argument('end', type=str, help='Ending git hash')
    parser.add_argument('directories', type=str, nargs='+',
                         help='Space delimited list of boardfarm directories')
    parser.add_argument('--debug', action='store_true',
                        help='Display much more info')
    try:
        args = parser.parse_args()
    except:
        parser.print_help()
        sys.exit(0)

    test_code_loc = []
    for d in args.directories:
        if d.endswith("boardfarm"):
            d = os.path.join(d, "boardfarm")
        test_code_loc.append(os.path.join(d, "tests", "*.py"))
    git_loc = [os.path.join(x, ".git") for x in args.directories]
    valid_test_types = ['rootfs_boot.RootFSBootTest']

    all_classes = get_all_classes_from_code(test_code_loc, debug=args.debug)
    all_classes = replace_parent_with_grandparent(all_classes,
                                                  no_modify=valid_test_types,
                                                  debug=args.debug)
    all_changed_classes = changed_classes(git_loc,
                                          args.start,
                                          args.end,
                                          debug=args.debug)

    features = get_features(git_loc, args.start, args.end, debug=args.debug)

    # Print all valid tests with a '-e ' in front of them for bft
    final_result = []
    for name in all_changed_classes:
        parent_type = all_classes.get(name, None)
        if parent_type in valid_test_types:
            final_result.append(name)
    print(" -e ".join([''] + final_result) + " -q ".join([''] + features))
