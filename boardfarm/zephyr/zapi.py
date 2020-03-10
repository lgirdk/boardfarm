#!/usr/bin/python2
""""Methods to interact with the Zephyr API on top of Jira"""
import re

from requests import get, post, put
from simplejson import loads

STATUS_CODE_DICT = {
    'SCHEDULED': -1,
    'PASS': 1,
    'FAIL': 2,
    'WORK IN PROGRESS': 3,
    'TEST SUSPENDED': 4,
    'ACCEPTED FAILED': 5,
    'NOT TESTED': 6,
    'BLOCKED': 7,
    'NA': 8,
    'DEPRECATED': 9,
    'PASSED WITH REMARKS': 10
}


class Zapi(object):
    """Zephyr API interface"""
    def __init__(self,
                 project_id=None,
                 version_id=None,
                 environment="",
                 build=None,
                 usr=None,
                 pwd=None,
                 jira_url=None):
        self._jira_url = jira_url
        self._zapi_url = self._jira_url + 'rest/zapi/latest/'
        self._zapi_hdr = {'Content-type': 'application/json'}
        self._proj_id = project_id
        self._vers_id = version_id
        self._environment = environment
        self._usr = usr
        self._pwd = pwd
        self._cycl_id = None
        self._build = build

    def create_cycle(self, name):
        """Creata a test cycle for the given projectid, versionid"""
        data = {
            "name": name,
            "projectId": self._proj_id,
            "versionId": self._vers_id,
            "environment": self._environment,
            "build": self._build
        }
        req_url = self._zapi_url + 'cycle'
        response = post(req_url,
                        json=data,
                        headers=self._zapi_hdr,
                        auth=(self._usr, self._pwd))
        data = loads(response.text)
        return data['id']

    def get_cycle_id(self, cycle_name):
        """Retrieve the cyccle id for a given Zephyr cycle name"""
        req_url = "{}cycle?projectID={}&versionId={}".format(
            self._zapi_url, self._proj_id, self._vers_id)
        response = get(req_url,
                       headers=self._zapi_hdr,
                       auth=(self._usr, self._pwd))
        data = loads(response.text)
        pattern = re.compile('-?\\d')
        for k in dict(data).keys():
            match = pattern.match(k)
            cycle_id = 0
            if match:
                cycle_id = int(k)
            if cycle_id > 0 and data[str(k)]['name'] == cycle_name:
                return k
        return ''

    def get_or_create_cycle(self, name):
        """Return the cycleId for a given cycle name
        If not found the cycle is created"""
        cycle_id = self.get_cycle_id(name)
        if not cycle_id:
            cycle_id = self.create_cycle(name)
        self._cycl_id = cycle_id

    def create_execution(self, test_id, assignee=None):
        """Create a Zephyr execution of the given test in the given project and
        release"""
        payload = {
            'projectId': self._proj_id,
            'cycleId': self._cycl_id,
            'issueId': test_id,
            'versionId': self._vers_id,
            'assigneeType': 'assignee',
            'assignee': assignee or self._usr
        }
        req_url = self._zapi_url + 'execution'
        response = post(req_url,
                        json=payload,
                        headers=self._zapi_hdr,
                        auth=(self._usr, self._pwd))
        data = loads(response.text)
        execution_id = dict(data).keys()[0]
        #execution_id = "442290"
        if response.status_code != 200:
            print("WARNING: " + response.text)
            print(req_url)
            print(payload)
        return execution_id

    def get_executions(self, test_id=None, assignee=None):
        """Create a Zephyr execution of the given test in the given project and
        release"""
        payload = {
            'projectId': self._proj_id,
            'cycleId': self._cycl_id,
            'issueId': test_id,
            'versionId': self._vers_id
        }
        req_url = self._zapi_url + 'execution'
        response = get(req_url,
                       params=payload,
                       headers=self._zapi_hdr,
                       auth=(self._usr, self._pwd))
        data = loads(response.text)
        executions = data.get('executions') or []
        return executions

    def set_execution_field(self, execution_id, field, value):
        """Set the execution status of a given test's executionid"""
        data = {field: value}
        req_url = self._zapi_url + 'execution/' + execution_id + '/'
        response = post(req_url,
                        params=data,
                        headers=self._zapi_hdr,
                        auth=(self._usr, self._pwd))
        if response.status_code != 200:
            print("WARNING: " + response.text)
            print(req_url)
            print(data)
        return response

    def set_execution(self,
                      exec_status,
                      execution_id,
                      comment="",
                      status_code_dict=STATUS_CODE_DICT):
        """Set the execution status of a given test's executionid"""
        data = {"status": status_code_dict[exec_status], "comment": comment}
        req_url = self._zapi_url + 'execution/' + execution_id + '/execute'
        response = put(req_url,
                       json=data,
                       headers=self._zapi_hdr,
                       auth=(self._usr, self._pwd))
        if response.status_code != 200:
            print("WARNING: " + response.text)
            print(req_url)
            print(data)
        return response
