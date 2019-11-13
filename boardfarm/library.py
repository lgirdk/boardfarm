# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import datetime
import ipaddress
import json
import os

from boardfarm.lib.common import print_bold

class HelperEncoder(json.JSONEncoder):
    '''Turn some objects into a form that can be stored in JSON.'''
    def default(self, obj):
        if isinstance(obj, ipaddress.IPv4Network) or \
           isinstance(obj, ipaddress.IPv4Address) or \
           isinstance(obj, ipaddress.IPv6Network) or \
           isinstance(obj, ipaddress.IPv6Address):
            return str(obj)
        elif isinstance(obj, datetime.datetime):
            return str(obj)
        elif hasattr(obj, 'shortname'):
            return obj.shortname()
        else:
            try:
                return json.JSONEncoder.default(self, obj)
            except:
                print("WARNING: HelperEncoder doesn't know how to convert %s to a string or number" % type(obj))
                return ""

def clean_for_json(data):
    '''
    Given a python dictionary, walk the structure and convert values to
    types that are valid for JSON. Return a python dictionary.
    '''
    return json.loads(json.dumps(data, cls=HelperEncoder))

def printd(data):
    '''Pretty-print as a JSON data object.'''
    print(json.dumps(data, sort_keys=True, indent=4, cls=HelperEncoder))

def check_devices(devices, func_name='check_status'):
    '''
    For each device, run a frunction. Useful to see if devices are still
    alive, running well, or whatever status function you wish to run.
    '''
    print('\n' + '='*20 + ' BEGIN Status Check ' + '='*20)
    for d in devices:
        if d is None:
            continue
        if hasattr(d, func_name):
            # The next line is kind of like doing: d.func_name()
            # This allows 'func_name' to be any string.
            try:
                getattr(d, func_name)()
            except:
                print("Status check for %s failed." % d.__class__.__name__)
        elif 'BFT_DEBUG' in os.environ:
            print("Pro Tip: Write a function %s.%s() to run between tests." %
                  (d.__class__.__name__, func_name))
    print('\n' + '='*20 + ' END Status Check ' + '='*20)

def process_test_results(raw_test_results, golden={}):
    full_results = {'test_results': [],
                    'tests_pass': 0,
                    'tests_fail': 0,
                    'tests_skip': 0,
                    'tests_total': 0,
                    'unexpected_fail': 0,
                    'unexpected_pass': 0,
                    }
    for i, x in enumerate(raw_test_results):
        def parse_and_add_results(cls, prefix=""):
            name = prefix + getattr(cls, 'name', cls.__class__.__name__)
            grade = getattr(cls, 'result_grade', None)
            try:
                if hasattr(cls, 'elapsed_time'):
                    elapsed_time = getattr(cls, 'elapsed_time')
                else:
                    start_time = getattr(cls, 'start_time')
                    stop_time = getattr(cls, 'stop_time')
                    elapsed_time = stop_time - start_time
            except:
                elapsed_time = 0

            unexpected = False
            if '_source' in golden:
                if name + "-result" in golden['_source']:
                    if golden['_source'][name + "-result"] != grade:
                        unexpected = True

            if grade == "Unexp OK" or (grade == "OK" and unexpected):
                grade = "Unexp OK"
                full_results['unexpected_pass'] += 1
            elif grade == "Exp FAIL" or (grade == "FAIL" and not unexpected):
                grade = "Exp FAIL"
                full_results['unexpected_fail'] += 1
            elif grade == "OK":
                full_results['tests_pass'] += 1
            elif grade == "FAIL":
                full_results['tests_fail'] += 1
            elif grade == "SKIP" or grade is None:
                full_results['tests_skip'] += 1

            message = getattr(cls, 'result_message', None)

            if message is None:
                try:
                    message = cls.__doc__.split('\n')[0]
                except:
                    message = "Missing description of class (no docstring)"
                    print_bold("WARN: Please add docstring to %s." % cls)
                    pass

            long_message = getattr(cls, 'long_result_message', "")

            full_results['test_results'].append({"name": name, "message": message, "long_message": long_message, "grade": grade, "elapsed_time": elapsed_time})

        try:
            parse_and_add_results(x)

            for subtest in x.subtests:
                parse_and_add_results(subtest, prefix=x.__class__.__name__ + "-")
        except Exception as e:
            print("Failed to parse test result: %s" % e)
            pass

    full_results['tests_total'] = len(raw_test_results)
    return full_results

def send_results_to_myqsl(testsuite, output_dir):
    '''
    Send url of results to a MySQL database.  Only do this if we are on
    a build server (use the build environment variables).
    '''
    dir = output_dir.replace(os.getcwd(), '').strip(os.sep)
    build_id = os.environ.get('image_build_id', '')
    build_url = os.environ.get('BUILD_URL', '')
    if '' not in (build_id, testsuite, build_url):
        from boardfarm.devices import mysql
        build_url = build_url.replace("https://", "") + "artifact/openwrt/%s/results.html" % dir
        title = 'Board Farm Results (suite: %s)' % testsuite
        reporter = mysql.MySqlReporter()
        reporter.insert_data(build_id, build_url, title)
