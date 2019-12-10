#!/usr/bin/env python

import argparse
import glob
import os
import re
import subprocess
import sys

import boardfarm


def get_all_classes_from_code(directories, debug=False):
    '''
    Uses 'grep' to find all files of type '.py' in the given directories.
    Then parses those files to return a dict where:
         * keys = class names
         * values = list with "parent class name" and "grandparent class name"
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
    # Create a list of tuples (classname, parent_classname)
    result = re.findall('class\s(\w+)\(([\w\.]+)\):', raw_text)
    #print(result)
    # Convert that list into a Python dict such that
    #    {"classname1": [parent_classname1,],
    #     "classname2": [parent_classname2,], ... etc}
    # Because we will add parents to that list.
    all_classes = dict([(x[0], [x[1],]) for x in result])
    # Add grandparent class
    for name in all_classes:
        parent = all_classes[name][0]
        if parent not in all_classes:
            continue
        grandparent = all_classes[parent][0]
        all_classes[name].append(grandparent)
    if debug:
        print("Found %s python classes." % len(all_classes))
        #for name in sorted(all_classes):
        #    print("%30s: %s" % (name, ", ".join(all_classes[name])))
    return(all_classes)

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
        print("\nAll directly changed classes from %s to %s:" % (start, end))
        for name in sorted(result):
            print("  %s : %s" % (name, result[name]))
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
    parser.add_argument('--debug', action='store_true',
                        help='Display much more info')
    try:
        args = parser.parse_args()
    except:
        parser.print_help()
        sys.exit(0)

    # Find locations of 'tests' subdirectories
    all_boardfarm_dirs = [os.path.dirname(boardfarm.plugins[m].__file__) for m in sorted(boardfarm.plugins)]
    all_boardfarm_dirs.append(os.path.dirname(boardfarm.__file__))
    test_code_loc = []
    for d in sorted(all_boardfarm_dirs):
        tmp = glob.glob(os.path.join(d, 'tests')) + \
              glob.glob(os.path.join(d, '*', 'tests'))
        if len(tmp) == 1:
            test_code_loc.append(os.path.join(tmp[0], '*.py'))
        elif len(tmp) > 1:
            print("Error in %s" % d)
            print("  Multiple 'tests' subdirectories found. There should only be "
                  "one 'tests' directory per project.")
            sys.exit(1)
    # Locations of '.git' files
    git_loc = [os.path.abspath(os.path.join(d, os.pardir, ".git")) for d in all_boardfarm_dirs]
    valid_test_types = 'rootfs_boot.RootFSBootTest'

    # Get a dictionary of the form
    #     {"classname": ["parent_classname", "grandparent_classname"], ... }
    all_classes = get_all_classes_from_code(test_code_loc, debug=args.debug)

    # Find names of all *directly* changed classes
    all_changed_classes = changed_classes(git_loc,
                                          args.start,
                                          args.end,
                                          debug=args.debug)
    # Add names of *indirectly* changed classes (child classes of changed classes)
    indirectly_changed_classes = {}
    for name, parents in all_classes.iteritems():
        if parents[0] in all_changed_classes.keys():
            indirectly_changed_classes[name] = all_classes[name]
    if args.debug:
        print("\nAll indirectly changed classes:")
        print("  " + "\n  ".join(indirectly_changed_classes))
    all_changed_classes.update(indirectly_changed_classes)

    features = get_features(git_loc, args.start, args.end, debug=args.debug)

    # Print all valid tests with a '-e ' in front of them for bft
    final_result = []
    for name in sorted(all_changed_classes):
        parents = all_classes.get(name, [])
        if valid_test_types in parents:
            final_result.append(name)
    if args.debug:
        print("\nFinal output including directly and indirectly changed tests:")
    print(" -e ".join([''] + final_result) + " -q ".join([''] + features))
