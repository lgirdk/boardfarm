#!/usr/bin/python2
import argparse
import os
import sys
import re
import csv
import datetime
import json
from pprint import pprint
from time import gmtime, strftime
from jira import JIRA
import zapi
from jira import JIRA
import requests

COLUMN_SCRIPT_NAME="TestScript Name"
COLUMN_JIRA_TEST_ID="Jira ID"

def parse_arguments():
    """Parses imput arguments and returns them to the main routine.
        Also takes care of prompting help"""
    parser = argparse.ArgumentParser(
        description='Post TDK Framework execution results to Zephyr (Jira)',
        epilog="i.e. %(prog)s")
    parser.add_argument("--report", "-rf",
                        help="The TDK Framework output file. \
                              Default: output.xml",
                        default="output.xml")
    parser.add_argument("--metafile", "-mf",
                        help="The csv file containing TDK tests and test case IDs \
                             Default: tdktests.csv",
                        default="tdktests.csv")
    parser.add_argument("--project", "-pr",
                        help="The Jira project where to update the results \
                              Default: RDK-B",
                        default="RDKB")
    parser.add_argument("--release", "-r",
                        help="The release version in Jira",
                        default="7.6.1")
    parser.add_argument("--environment", "-e", required=False,
                        help="A string that identifies the environment.",
                        default="Lab 5C")
    parser.add_argument("--cycle", "-c", required=False,
                        help="The name of the test cycle. \
                        When not given, the cycle gets the name of the build",
                        default=None)
    parser.add_argument("--build", "-b", required=False,
                        help="The build (software version) under test. \
                        A cycle with this name is created if not otherwise \
                        specified", default = "DemoBuild")
    parser.add_argument("--user", "-u", required=False,
                        help="The Jira user that is publishing the results", default = USR)
    parser.add_argument("--passwd", "-p", required=False,
                        help="The Jira password of the given user", default = PWD)
    parser.add_argument("--updateautomationstatus", "-a", required=False,
                        help="When True it marks the test automation status \
                        in Jira",
                        action="store_true")

    args = parser.parse_args()
    return args

def get_jira_release_id(rel_name, jira, proj):
    """Return the ID of the release in a given project"""
    versions = jira.project_versions(proj)
    for version in reversed(versions):
        if version.name == rel_name:
            return version.id

    raise Exception("Failed to get version id for release %s" % rel_name)


def update_automation_status(issue):
    """Update the Jira custom field to track that the test is automated"""
    #if issue.fields.customfield_11640.value != 'Automated test':
    #    issue.update(fields={'customfield_11640': {'value': 'Automated test'}})
    #return


def get_test_id_from_meta_file(meta_file, test_name):
    reader = csv.DictReader(open(meta_file))
    test_id = ""
    for row in reader:
        if row["TestScript Name"] == test_name:
            test_id = row[COLUMN_JIRA_TEST_ID]
    return test_id

def parse_zapi_config():
    data = []
    if 'BFT_OVERLAY' in os.environ:
        for overlay in os.environ['BFT_OVERLAY'].split(' '):
            zdir = os.path.join(os.path.abspath(overlay), 'zephyr')
            if os.path.exists(zdir):
                data.append(json.load(open(os.path.join(zdir, 'zapi_configuration.json'))))
                data[-1]['metafile'] = os.path.join(zdir, 'boardfarm_tc_meta_file.csv')

    # TODO: opensource zephyr for boardfarm tests?
    if os.path.exists('zephyr/zapi_configuration.json'):
        data.append(json.load(open('zephyr/zapi_configuration.json')))

    return data

def update_zephyr(test_cases_list):
    args=parse_zapi_config()
    if len(args) == 0:
        print("Zephyr is not configured, skipping...")
        return
    print('Starting Zephyr Execution....')

    for z in args:
        if "JIRA_URL" == z['jira_url'] or "JIRAPASSWORD" == z['passwd']:
            # This is not configure, skip to next
            continue

        """"Main routine"""

        jira = JIRA(basic_auth=(z["user"], z["passwd"]),
                    options={'server': z["jira_url"]})

        proj = jira.project(z["project"])
        verid = get_jira_release_id(z['release'], jira, proj)
        cycleName = z["cycle"]
        cycleName = cycleName + "_" + str((datetime.datetime.now()).strftime("%Y%m%d%H%M%S"))


        reporter = zapi.Zapi(project_id=proj.id,
                             version_id=verid,
                             environment=str(z["environment"]),
                             build=z["build"],
                             jira_url=z["jira_url"],
                             usr=z["user"],
                             pwd=z["passwd"])
        if z["cycle"] is None:
            z["cycle"] = z["build"]
        reporter.get_or_create_cycle(str(cycleName))

        result = ""

        for i in range(len(test_cases_list)):
            test_name = test_cases_list[i][0]
            print("Test_name :" + test_name)
            test_id = get_test_id_from_meta_file(z["metafile"], test_name)

            if test_id:
                print("Found Test ID in Meta file : " + test_id)
                issue = jira.issue(test_id)
            else:
                continue

            if z["updateautomationstatus"]:
                 update_automation_status(issue)

            exec_id = reporter.create_execution(str(issue.id))
            result = test_cases_list[i][1]
            print("Test case Result: " + result)
            log_data = "sample log data"
            if result == 'FAIL':
                result = 'FAIL'
            if result == 'OK':
                result = 'PASS'
            if result == 'None':
                result = 'FAIL'
            if result == 'SKIP':
                result = 'NOT TESTED'
            if result == 'Exp FAIL':
                result = 'FAIL'

            if 'status_codes' in z:
                ret = reporter.set_execution(result,
                 exec_id,
                 log_data,
                 status_code_dict=z['status_codes'])
            else:
                ret = reporter.set_execution(result,
                 exec_id,
                 log_data)

            if ret.status_code != requests.codes.ok:
                raise Exception("Error = %s, when trying to set execution status" % ret)

if __name__ == "__main__":
    ARGS = parse_arguments()
    main(ARGS)
