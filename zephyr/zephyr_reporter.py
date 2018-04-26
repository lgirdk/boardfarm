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

try:
    from lxml import etree
    print "running with lxml.etree"
except ImportError:
    try:
        # Python 2.5
        import xml.etree.cElementTree as etree
        print "running with cElementTree on Python 2.5+"
    except ImportError:
        try:
            # Python 2.5
            import xml.etree.ElementTree as etree
            print "running with ElementTree on Python 2.5+"
        except ImportError:
            try:
                # normal cElementTree install
                import cElementTree as etree
                print "running with cElementTree"
            except ImportError:
                try:
                    # normal ElementTree install
                    import elementtree.ElementTree as etree
                    print "running with ElementTree"
                except ImportError:
                    print "Failed to import ElementTree from any known place"

"""
Settings file to interact with LG's Jira
Key parameters are USR and PWD
"""

"""./zephyr_reporter.py -mf currently_published.csv -b "DemoBuild" -a -u username -p password
    1) "--report", "-rf" : The TDK Framework output file.Default: output.xml.
    2) "--metafile", "-mf" : The csv file containing TDK tests and test case IDs. Default: tdktests.csv.
    3) "--project", "-pr" : The Jira project where to update the results. Default: ARRISEOS.
    4) "--release", "-r" : The release version in Jira. Default="9.9.99".
    5) "--environment", "-e" : A string that identifies the environment. Default="Lab 5C"
    6) "--cycle", "-c" : The name of the test cycle. When not given, the cycle gets the name of the build. Default=None
    7) "--build", "-b" : The build (software version) under test. A cycle with this name is created if not otherwise specified.
    8) sunglasses: "--user", "-u" : The Jira user that is publishing the results.
    9) "--passwd", "-p" : The Jira password of the given user.
    10) "--updateautomationstatus, -a" : When True it marks the test automation status in Jira.

"""			
					
from jira import JIRA
import zapi
from jira import JIRA

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
        #if version.name == rel_name:
            version.id = "32880"
            return version.id
    #return ''


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
	data = json.load(open('zephyr/zapi_configuration.json'))
	return data

	length = len(data["test_results"])

	for len in range(0, length):

		test_case = data["test_results"][len]["name"]

def update_zephyr(test_cases_list):
    args=parse_zapi_config()

    """"Main routine"""

    jira = JIRA(basic_auth=(args["user"], args["passwd"]),
                options={'server': args["jira_url"]})

    proj = jira.project(args["project"])
    #verid = get_jira_release_id(args.release, jira, proj)
    verid = "32880"
    cycleName = args["cycle"]
    cycleName = cycleName + "_" + str((datetime.datetime.now()).strftime("%Y%m%d%H%M%S"))


    reporter = zapi.Zapi(project_id=proj.id,
                         version_id=verid,
                         environment=str(args["environment"]),
                         build=args["build"],
                         jira_url=args["jira_url"],						
                         usr=args["user"],
                         pwd=args["passwd"])
    if args["cycle"] is None:
        args["cycle"] = args["build"]
    reporter.get_or_create_cycle(str(cycleName))

    result = ""

    for i in range(len(test_cases_list)):
        test_name = test_cases_list[i][0]
        print "Test_name :" + test_name
        test_id = get_test_id_from_meta_file(args["metafile"], test_name)

        if test_id:
            print "Found Test ID in Meta file : " + test_id
            issue = jira.issue(test_id)
        if args["updateautomationstatus"]:
             update_automation_status(issue)

        exec_id = reporter.create_execution(str(issue.id))
        result = test_cases_list[i][1]
        print "Test case Result: " + result
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

        reporter.set_execution(result,
         exec_id,
         log_data)
    
if __name__ == "__main__":
    ARGS = parse_arguments()
    main(ARGS)
