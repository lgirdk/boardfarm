#!/usr/bin/env python

import argparse
import glob
import os
import sys

import boardfarm
from boardfarm.lib.code import get_all_classes_from_code, changed_classes, get_features
from boardfarm.lib.code import get_classes_lib_functions, changed_functions

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
    valid_test_types = ('rootfs_boot.RootFSBootTest', 'BF_Test')

    # Get a dictionary of the form
    #     {"classname": ["parent_classname", "grandparent_classname"], ... }
    all_classes = get_all_classes_from_code(test_code_loc, debug=args.debug)

    # Get a dictionary with classnames as keys, and list of functions they import and use
    #     {"classname": ['function1', 'function2', ... }
    all_classes_and_funcs = get_classes_lib_functions(test_code_loc, debug=args.debug)

    # Find names of all *directly* changed classes
    all_changed_classes = changed_classes(git_loc,
                                          args.start,
                                          args.end,
                                          debug=args.debug)

    # Find names of all *directly* changed functions
    all_changed_functions = changed_functions(git_loc,
                                              args.start,
                                              args.end,
                                              debug=args.debug)

    # Add names of *indirectly* changed classes (child classes of changed classes)
    indirectly_changed_classes = {}
    for name, parents in all_classes.items():
        if parents[0] in all_changed_classes.keys():
            indirectly_changed_classes[name] = all_classes[name]
    # Add names of *indirectly* changed classes because functions were changed
    for name, funcs in all_classes_and_funcs.items():
        if set(funcs) & set(all_changed_functions):
            if name in all_classes:
                # Disable temporarily the running of tests from a function change.
                # We need to filter to stable, short tests. Or have that option.
                #indirectly_changed_classes[name] = all_classes[name]
                pass
    if args.debug:
        print("\nAll indirectly changed classes (either through a function change or subclass change):")
        print("  " + "\n  ".join(indirectly_changed_classes))
    all_changed_classes.update(indirectly_changed_classes)

    features = get_features(git_loc, args.start, args.end, debug=args.debug)

    filter_name = '_TST_'
    if args.debug:
        print("\nWill filter to only test names containing '%s'." % filter_name)

    # Print all valid tests with a '-e ' in front of them for bft
    final_result = []
    for name in sorted(all_changed_classes):
        if filter_name not in name:
            continue
        parents = all_classes.get(name, [])
        for v in valid_test_types:
            if v in parents:
                final_result.append(name)
                break
    if args.debug:
        print("\nFinal output including directly and indirectly changed tests:")
    print(" -e ".join([''] + final_result) + " -q ".join([''] + features))
