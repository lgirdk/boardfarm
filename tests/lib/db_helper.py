# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.


from influxdb import InfluxDBClient
import os, re, json, pexpect
from datetime import datetime, timedelta
import sys

db_config_example = {
    "db_host": "10.64.38.3",
    "db_port": 8086,
    "db_username": "root",
    "db_password": "root",
    "database": "quickdemo",
    "server_logs": "logs\\test_dir",
    "client_logs": "logs\\clientlogs",
    "test_run": 1,
    "board": "mv1-2-9"
}

def datetimetostr(dt):
    if dt.utcoffset() is None:
        return "%sZ" % dt.isoformat()
    if dt.utcoffset() == datetime.timedelta(0):
        return "%sZ" % dt.replace(tzinfo=None).isoformat()
    return dt.isoformat()

class Influx_DB_Logger(InfluxDBClient):
    """Allows to create, update, an influx db table"""
    debug = True
    board = None

    # a template helper for influxdb
    measurement_templatedic={
        "measurement": "XXX",
        "tags": {
            "board": "XXX",
            "test_run": "n"
        },
        "time": "",
        "fields": {}
    }

    def __init__(self, **kwargs):
        self.port = kwargs.get("db_port", 8086)
        self.host = kwargs.get("db_host", "localhost")
        self.username = kwargs.get("db_username", "root")
        self.password = kwargs.get("db_password", "root")
        self.database = kwargs.get("database", None)
        assert self.database is not None, "Failed: database in None"
        self.board = kwargs.get("board", None)

        self.db_data = []

        super(Influx_DB_Logger, self).__init__(
            port=self.port,
            host=self.host,
            username=self.username,
            database=self.database,
            password=self.password
        )

        # need to validate if DB is present, if not we need to create.
        self.validate_db(self.database)
        self.switch_database(self.database)
        print("Client Initialized!")

    def validate_db(self, db_name):
        for i in self.get_list_database():
            if i["name"] == db_name:
                print("Info: %s db validated..." % str(db_name))
                return True

        print("Error: %s not found. Creating DB..." % str(db_name))
        self.create_database(db_name)

    # this function works on the iperf logs once the iperf run has completed
    # hence not "realtime"
    def add_iperf_server_logs(self, measurement, log_dir, test_run=1, board="mv1-1-1"):
        for file in os.listdir(log_dir):

            log_file = os.path.join(log_dir, file)
            start_time = datetime.fromtimestamp(os.path.getctime(log_file))
            with open(log_file, "r") as fp:
                log_content = [j.strip().split("\n") for j in "\n".join(
                    [i.strip() if not i.startswith("-") else "#"
                     for i in fp.read().split("\n") if i.strip() != ""]).split("#") if j.strip() != ""]
            listen_port = log_content[0][0].split(" ")[-1]
            for i in range(1,len(log_content),3):
                fields = [field for field in log_content[i][2].split(" ") if field != ""][2::]
                fields = fields[0:-2] + [" ".join(fields[-2::])]
                for j in range(3, len(log_content[i])):
                    temp = [value for value in log_content[i][j].split(" ") if value != ""][2::]
                    values = [float(temp[0].split("-")[0]), float(temp[2]), float(temp[4]), int(temp[6])]
                    data_unit = {
                        "measurement": measurement,
                        "tags": {
                            "board": board,
                            "test_run": test_run,
                            "location": "server",
                            "port": listen_port
                        },
                        "time": datetimetostr(start_time+timedelta(seconds=float(values[0]))),
                        "fields": dict(zip(fields,values))
                    }
                    self.db_data.append(data_unit)
            print("DB updating : %r" % self.write_points(self.db_data))

    def populate_result_dictionary(self, data_field, cmd, iteration, date):

        body = self.measurement_templatedic.copy()
        body['fields'] = data_field
        body.pop('time') # at the moment we use the db update time
        body['measurement'] = cmd
        body['tags']['board'] = self.board
        body['tags']['test_run'] = iteration
        return body

    # jsonifies a table like ps, netstat, etc, where the 1st row shows the keys
    def process_table(self, datain, cmd, iteration, date, mode='join'):
        if self.debug:
            print datain
        # the first line is the db colums headers
        keys=datain[0].split()
        if self.debug:
            print "keys=",keys

        # loops through the rows
        for elem in datain[1:]:
            l=elem.split()

            # but the last value might have several fields hence join them
            # or maybe missing (e.g. netstat udp have no state) hence sets them to null
            if len(keys)<=len(l):
                if mode == 'join':
                    l[len(keys)-1:] = [' '.join(l[len(keys)-1:])]
                elif mode == 'drop':
                    l= l[:len(keys)] # drops any additional values
            else:
                for i in range(len(l),len(keys)):
                    l.append('null')

            # key:value pairs
            res_dict = dict(zip(keys, l))
            res_dict['date'] = date
            body = self.populate_result_dictionary(res_dict, cmd, iteration, date)
            self.db_data.append(body)
            print json.dumps(body, indent=4)
            print("process_table: body: %s DB updating: %r" %  (json.dumps(body, indent=4),self.write_points([body])))

        if self.debug:
            print json.dumps(self.db_data,indent=4)

    def send_to_db(self, datain, cmd, iteration, date):
        """
        whith this function we can send data to the db in "realtime"
        i.e. we run a command like ps on the station, and the results 
        can be posted immediately
        """
        # the mode allows to either join or drop the trailing columns
        # i.e. in ps the command has 5 cloumns (PID, user, etc), and
        # the las column can have trailing values (the actual command)
        #mode = 'join' if 'mode' not  in cmd_dict[cmd] else cmd_dict[cmd]['mode']
        mode = 'join'
        # just get the part of the command up to the |
        command = cmd[:cmd.index('|')] if '|' in cmd else cmd

        self.process_table(datain, command, iteration, date, mode)

