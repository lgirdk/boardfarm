Zephyr Integration with boardfarm:
===================================
Zephyr is an add-on for Jira that allows us to integrate test management into the one system.

Folder and file structure follows as below for the integration of Zephyr with boardfarm

1. boardfarm_tc_meta_file.csv
   Meta file which has the mapping between Boardfarm test cases with JIRA test cases

2. zapi_configuration.json
   Configuration file which has the basic configuration settings for Zephyr, main values as follows,

       1. metafile   : "zephyr/boardfarm_tc_meta_file.csv"
               Meta file location which has the mapping between boardfarm test cases with JIRA cases
       2. project    : "RDKB"
               JIRA projet name in which JIRA tickets has been created
       3. release"   : "7.6.1"
               JIRA relase version
       4. cycle      : "Demo-zephyr-cycle"
               Zephyr cycle name for the test cases execution. Set of all testcase execution result will be updated in a single cycle in Zephyr
       5. build      : "DemoBuild"
               Specify the build name, boardfarm testcases are testing against.
       6. Jira_url   : "JIRAURL"
       7. user       : "JIRAuser"
       8. passwd     : "JIRApasswd",
               Username and password to access JIRA

3. zapi.py
   Rest Api for Zephyr Functionlities

4. zephyr_reporter.py
    Code to update the reault data from boardfarm execution to Zephyr
