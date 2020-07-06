#!/usr/bin/env python
# Code Author: https://github.com/CVCLabs/
# Project: https://github.com/CVCLabs/sonar-jira-integration

import os

import pandas as pd
import requests
from jira import JIRA

sonar_user = os.getenv("SONAR_USER")
sonar_pass = os.getenv("SONAR_PWD")
sonar_base_url = os.getenv("SONAR_URL")
sonar_projects = os.getenv("SONAR_PROJ")
sonar_branch = os.getenv("SONAR_BRANCH")
sonar_issue_type = os.getenv("SONAR_ISSUE_TYPE")
jira_base_url = os.getenv("JIRA_URL")
jira_user = os.getenv("JIRA_USER")
jira_pass = os.getenv("JIRA_PWD")
jira_project = os.getenv("JIRA_PROJ")
sonar_auth_url = sonar_base_url.replace("//", f"//{sonar_user}:{sonar_pass}@")
jira_epic = os.getenv("JIRA_EPIC", "")


def main():
    """Drives the script flow. Returns dataframe table with 'Sonarqube_id',
       'Jira_id', 'comments' columns
       Gets the issue_matrix containing the issues created and prints it.
    """
    issue_matrix = get_sonar_jira_issues()
    print(issue_matrix)


def get_jira_id_in_comments(comments):
    """Function to check whether Jira id's are already mentioned in comments
       of sonarqube issues.

    :return: returns the jira_id if jira url is present in comments
             else returns False
    :rtype: String or Boolean
    """
    for comment in comments:
        if jira_base_url in comment["markdown"]:
            text = comment["markdown"]
            lines = text.split()
            for line in lines:
                if line.startswith(jira_base_url):
                    jira_id = line.split("/")[-1]
                    if jira_project in jira_id:
                        return jira_id
    return False


def get_sonar_jira_issues():
    """Gets all the sonarqube issue based on the issue type and
       1. Check Jira is already created for every issue.
       2. If not call create_jira_issue function to create new Jira issue
       3. Add rows to issue_matrix with sonar_issue, Jira and comments

    :return: issue_matrix
    :rtype: DataFrame
    """
    issue_matrix = pd.DataFrame(
        [], columns=["Sonarqube_id", "Jira_id", "comments"])

    try:
        sonar_issues = []
        projects_list = sonar_projects.split(",")
        issue_type_list = sonar_issue_type.split(",")
        for sonar_project in projects_list:
            for issue_type in issue_type_list:
                response = requests.get(
                    sonar_auth_url +
                    "/api/issues/search?additionalFields=comments&types=" +
                    sonar_issue_type + "&projects=" + sonar_project +
                    "&branch=" + sonar_branch +
                    "&statuses=OPEN,REOPENED,CONFIRMED")
                data_json = response.json()
                sonar_issues = sonar_issues + data_json["issues"]

    except Exception as e:
        print(e)

    for issue in sonar_issues:
        existing_jira_id = get_jira_id_in_comments(issue["comments"])
        if existing_jira_id:
            issue_matrix.loc[-1] = [issue["key"], existing_jira_id, ""]
        else:
            Jira_id = create_jira_issue(issue)
            comment = ""
            if Jira_id:
                response = requests.post(sonar_auth_url +
                                         "/api/issues/add_comment?issue=" +
                                         issue["key"] + "&text=" +
                                         jira_base_url + "/browse/" + Jira_id)
                if not response.ok:
                    comment = "Unable to add Jira URL to issue in Sonarqube"
                issue_matrix.loc[-1] = [issue["key"], Jira_id, comment]
            else:
                issue_matrix.loc[-1] = [
                    issue["key"],
                    "Jira id was not created due to earlier exception",
                    comment,
                ]
        issue_matrix.index = issue_matrix.index + 1
        issue_matrix = issue_matrix.sort_index()

    return issue_matrix


def create_jira_issue(issue):
    """Creates new jira ticket for sonarqube issue

    :return: New Jira id created else returns False
    :rtype: String or Boolean
    """
    try:
        jira = JIRA(server=jira_base_url, basic_auth=(jira_user, jira_pass))

        labels = issue["tags"]
        labels.extend([issue["project"]])

        description = ("Triggering rule:\n" + issue["message"] + "\nLink: "
                       "" + sonar_base_url + "/issues?issues=" + issue["key"])

        if "author" in issue.keys():
            description += "\nAuthor: " "" + issue["author"]

        issue_dict = {
            "project": {
                "key": jira_project
            },
            "summary": "[SonarQube] - " + issue["component"],
            "description": description,
            "issuetype": {
                "name": "Bug"
            },
            "priority": {
                "name": get_priority(issue["severity"])
            },
            "labels": ["SonarQube"],
            "customfield_12072": [{
                "value": "Low"
            }],
            "customfield_10530": jira_epic,
        }

        new_issue = jira.create_issue(fields=issue_dict)
        return new_issue.key

    except Exception as e:
        print("Exception on create_jira_issue: " + str(e) + "\n")
        return False


def get_priority(severity):
    """Returns priority to be added in Jira based on Sonarqube issue priority

    :return: Jira priority
    :rtype: String
    """
    if severity in ("BLOCKER", "CRITICAL"):
        return "Major (P2)"

    elif severity == "MAJOR":
        return "Minor (P3)"

    elif severity in ("MINOR", "INFO"):
        return "Not Blocking (P4)"

    else:
        return "Unprioritised"


if __name__ == "__main__":
    main()
