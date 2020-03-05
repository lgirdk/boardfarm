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
import traceback

import boardfarm
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
                print(
                    "WARNING: HelperEncoder doesn't know how to convert %s to a string or number"
                    % type(obj))
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


def get_test_name(test, override_name=None):
    if hasattr(test, 'override_kibana_name'):
        n = test.override_kibana_name
    elif override_name is not None:
        n = override_name
    elif hasattr(test, 'name'):
        n = test.name
    else:
        n = test.__class__.__name__

    return n


def generate_test_info_for_kibana(test, prefix="", override_name=None):
    '''
    Given a test, returns a nice name and a dictionary of information
    to log for that test.
    '''

    if override_name is not None:
        n = override_name
    else:
        n = prefix + get_test_name(test) + '-'

    result = {}
    for k, v in test.logged.items():
        result[n + k] = v
    if hasattr(test, 'result_grade'):
        result[n + "result"] = test.result_grade
    return result


def check_devices(devices, func_name='check_status'):
    '''
    For each device, run a frunction. Useful to see if devices are still
    alive, running well, or whatever status function you wish to run.

    Returns a list of devices where the check failed
    '''
    ret = []

    print('\n' + '=' * 20 + ' BEGIN Status Check ' + '=' * 20)
    for d in devices:
        if d is None:
            continue
        if hasattr(d, func_name):
            # The next line is kind of like doing: d.func_name()
            # This allows 'func_name' to be any string.
            saved_logfile_read = None
            try:
                if hasattr(d, 'logfile_read'):
                    saved_logfile_read = d.logfile_read.out
                    d.logfile_read.out = None
                print("Checking status for " + d.__class__.__name__ +
                      " (see log in result dir for data)")
                getattr(d, func_name)()
            except:
                ret.append(d)
                print("Status check for %s failed." % d.__class__.__name__)
            if saved_logfile_read is not None:
                d.logfile_read.out = saved_logfile_read
        elif 'BFT_DEBUG' in os.environ:
            print("Pro Tip: Write a function %s.%s() to run between tests." %
                  (d.__class__.__name__, func_name))
    print('\n' + '=' * 20 + ' END Status Check ' + '=' * 20)

    return ret


def process_test_results(raw_test_results, golden={}):
    full_results = {
        'test_results': [],
        'tests_pass': 0,
        'tests_fail': 0,
        'tests_skip': 0,
        'tests_total': 0,
        'unexpected_fail': 0,
        'unexpected_pass': 0,
    }

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

        unexpected = None
        if '_source' in golden:
            if name + "-result" in golden['_source']:
                if golden['_source'][name + "-result"] != grade:
                    unexpected = True
                else:
                    unexpected = False

        if grade == "Unexp OK" or (grade == "OK" and unexpected == True):
            grade = "Unexp OK"
            full_results['unexpected_pass'] += 1
        elif grade == "Exp FAIL" or (grade == "FAIL" and unexpected == False):
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

        full_results['test_results'].append({
            "name": name,
            "message": message,
            "long_message": long_message,
            "grade": grade,
            "elapsed_time": elapsed_time
        })

    for i, x in enumerate(raw_test_results):
        try:
            parse_and_add_results(x)

            for subtest in x.subtests:
                parse_and_add_results(subtest,
                                      prefix=x.__class__.__name__ + "-")
        except Exception as e:
            print("Failed to parse test result: %s" % e)
            pass

    full_results['tests_total'] = len(raw_test_results)
    return full_results


def create_results_html(full_results, config, logger):
    '''Creates results.html from config and test results'''

    from boardfarm import make_human_readable
    try:
        title_str = make_human_readable.get_title()
        make_human_readable.xmlresults_to_html(full_results['test_results'],
                                               title=title_str,
                                               output_name=os.path.join(
                                                   config.output_dir,
                                                   "results.html"),
                                               board_info=config.board)
    except Exception as e:
        logger.debug(e)
        traceback.print_exc()
        logger.debug("Unable to create HTML results")


def create_info_for_remote_log(config, full_results, tests_to_run, logger,
                               env_helper):
    # Try to remotely log information about this run
    info_for_remote_log = dict(config.board)
    info_for_remote_log.update(full_results)
    info_for_remote_log['environment'] = getattr(env_helper, 'env', {})
    info_for_remote_log['bft_version'] = boardfarm.__version__
    info_for_remote_log['issue'] = 'bft_execution'

    if 'BUILD_URL' in os.environ:
        info_for_remote_log['jenkins_url'] = os.environ['BUILD_URL']
    else:
        info_for_remote_log['jenkins_url'] = None

    # TODO: move duration calculation outside of this function
    if 'TEST_END_TIME' in os.environ and 'TEST_START_TIME' in os.environ:
        info_for_remote_log['duration'] = int(
            os.environ['TEST_END_TIME']) - int(os.environ['TEST_START_TIME'])

    if hasattr(config, 'TEST_SUITE'):
        info_for_remote_log['test_suite'] = str(config.TEST_SUITE)

    # but we will add back specific test results data
    info_for_remote_log['execution'] = {}
    idx = 0
    for t in tests_to_run:
        data = generate_test_info_for_kibana(t, prefix="", override_name="")
        info_for_remote_log['test_results'][idx].update(data)
        for subtest in t.subtests:
            data = generate_test_info_for_kibana(subtest,
                                                 prefix="",
                                                 override_name="")
            info_for_remote_log['test_results'][idx].update(data)
            idx += 1
        idx += 1

    for item in info_for_remote_log['test_results']:
        item.pop('row_style')
        item.pop('style')

    # Convert python objects to things that can be stored in
    # JSON, like strings and numbers.
    info_for_remote_log = clean_for_json(info_for_remote_log)
    # Remove reserved key names
    info_for_remote_log.pop('_id', None)

    return info_for_remote_log
