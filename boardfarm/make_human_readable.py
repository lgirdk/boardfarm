#!/usr/bin/env python

# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import glob
import json
import os
import sys
import time
from string import Template

import boardfarm

try:
    from collections import Counter
except:
    from future.moves.collections import Counter

owrt_tests_dir = os.path.dirname(os.path.realpath(__file__))


def pick_template_filename():
    '''
    Decide which HTML file to use as template for results.
    This allows for different format for different audiences.
    '''

    basic = owrt_tests_dir + "/html/template_results_basic.html"
    full = owrt_tests_dir + "/html/template_results.html"
    for modname in sorted(boardfarm.plugins):
        overlay = os.path.dirname(boardfarm.plugins[modname].__file__)
        tmp = glob.glob(os.path.join(overlay, 'html', 'template_results_basic.html')) + \
              glob.glob(os.path.join(overlay, '*', 'html', 'template_results_basic.html'))
        if len(tmp) > 0 and os.path.isfile(tmp[0]):
            basic = tmp[0]
            break
        tmp = glob.glob(os.path.join(overlay, 'html', 'template_results.html')) + \
              glob.glob(os.path.join(overlay, '*', 'html', 'template_results.html'))
        if len(tmp) > 0 and os.path.isfile(tmp[0]):
            full = tmp[0]
            break

    templates = {'basic': basic, 'full': full}
    if os.environ.get('test_suite') == 'daily_au':
        return templates['basic']
    else:
        return templates['full']


def build_station_info(board_info):
    ret = ""

    for device in board_info[u'devices']:
        conn = device.get('conn_cmd', None)
        if not conn:
            conn = ":".join([device.get('ipaddr', ''), device.get('port', '')])
        ret += "    <li>%s %s %s</li>\n" % (device['name'], device['type'],
                                            conn)

    return ret


def xmlresults_to_html(test_results,
                       output_name=owrt_tests_dir + "/results/results.html",
                       title=None,
                       board_info={}):
    parameters = {
        'build_url': os.environ.get('BUILD_URL'),
        'total_test_time': 'unknown',
        'summary_title': title,
        "board_type": "unknown",
        "location": "unknown",
        "report_time": "RUNNING or ABORTED"
    }
    try:
        parameters.update(board_info)
        parameters['misc'] = build_station_info(board_info)
    except Exception as e:
        print(e)

    # categorize the results data
    results_table_lines = []
    results_fail_table_lines = []
    grade_counter = Counter()
    styles = {
        'OK': 'ok',
        'Unexp OK': 'uok',
        'SKIP': 'skip',
        None: 'skip',
        'FAIL': 'fail',
        'Exp FAIL': 'efail',
        'PENDING': 'skip',
        'TD FAIL': 'fail'
    }
    for i, t in enumerate(test_results):
        if t['grade'] is None:
            t['grade'] = 'PENDING'
        t['num'] = i + 1
        t['style'] = styles[t['grade']]
        if i % 2 == 0:
            t['row_style'] = "even"
        else:
            t['row_style'] = "odd"
        grade_counter[t['grade']] += 1
        if 'FAIL' == t['grade']:
            results_fail_table_lines.append(
                '<tr class="%(row_style)s"><td>%(num)s</td><td class="%(style)s">%(grade)s</td><td>%(name)s</td></tr>'
                % t)
        results_table_lines.append(
            '<tr class="%(row_style)s"><td>%(num)s</td><td class="%(style)s">%(grade)s</td><td>%(name)s</td><td>%(message)s</td><td>%(elapsed_time).2fs</td></tr>'
            % t)
        if t['long_message'] != "":
            results_table_lines.append(
                '<tr class="%(row_style)s"><td colspan=4><pre align="left">' %
                t)
            results_table_lines.append("%(long_message)s" % t)
            results_table_lines.append('</pre></td></tr>')

    # process the summary counter
    results_summary_table_lines = []
    for e, v in grade_counter.items():
        results_summary_table_lines.append(
            '<tr><td class="%s">%s: %d</td></tr>' % (styles[e], e, v))

    # Create the results tables
    parameters['table_results'] = "\n".join(results_table_lines)
    if len(results_fail_table_lines) == 0:
        parameters['table_fail_results'] = "<tr><td>None</td></tr>"
    else:
        parameters['table_fail_results'] = "\n".join(results_fail_table_lines)
    parameters['table_summary_results'] = "\n".join(
        results_summary_table_lines)

    # Other parameters
    try:
        test_seconds = int(os.environ.get('TEST_END_TIME')) - int(
            os.environ.get('TEST_START_TIME'))
        minutes = round((test_seconds / 60), 1)
        parameters['total_test_time'] = "%s minutes" % minutes
    except:
        pass

    # Report completion time
    try:
        end_timestamp = int(os.environ.get('TEST_END_TIME'))
        struct_time = time.localtime(end_timestamp)
        format_time = time.strftime("%Y-%m-%d %H:%M:%S", struct_time)
        parameters['report_time'] = "%s" % (format_time)
    except:
        pass

    # Substitute parameters into template html to create new html file
    template_filename = pick_template_filename()
    f = open(template_filename, "r").read()
    s = Template(f)
    f = open(output_name, "w")
    f.write(s.substitute(parameters))
    f.close()


def get_title():
    try:
        title = os.environ.get('summary_title')
        if title:
            return title
    except:
        pass
    try:
        return os.environ.get('JOB_NAME')
    except:
        return None


if __name__ == '__main__':
    try:
        list_results = json.load(open(sys.argv[1], 'r'))['test_results']
        xmlresults_to_html(list_results, title="Test Results")
    except Exception as e:
        print(e)
        print("To use make_human_readable.py:")
        print("./make_human_readable.py results/test_results.json")
