# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.


import json
from datetime import datetime, timedelta

from influxdb import InfluxDBClient


def datetimetostr(dt):
    if dt.utcoffset() is None:
        return f"{dt.isoformat()}Z"
    if dt.utcoffset() == datetime.timedelta(0):
        return f"{dt.replace(tzinfo=None).isoformat()}Z"
    return dt.isoformat()


class Influx_DB_Logger(InfluxDBClient, dict):
    """Allows to create, update, an influx db table"""

    debug = False
    board = None

    # a template helper for influxdb
    measurement_templatedic = {
        "measurement": "XXX",
        "tags": {"board": "XXX", "test_run": "n"},
        "time": "",
        "fields": {},
    }

    def __init__(self, **kwargs):
        self.port = kwargs.get("db_port", "8086")
        self.host = kwargs.get("db_host", None)
        self.username = kwargs.get("db_username", "root")
        self.password = kwargs.get("db_password", "root")
        self.database = kwargs.get("database", "stability")
        assert self.database is not None, "Failed: database in None"
        self.board = kwargs.get("board", kwargs["board"])
        self.test_run = kwargs.get("test_run", kwargs["test_run"])
        self.db_data = []

        super().__init__(
            port=self.port,
            host=self.host,
            username=self.username,
            database=self.database,
            password=self.password,
        )
        # need to validate if DB is present, if not we need to create.
        self.validate_db(self.database)
        self.switch_database(self.database)
        print("Client Initialized!")

    def validate_db(self, db_name):
        for i in self.get_list_database():
            if i["name"] == db_name:
                print(f"Info: {str(db_name)} db validated...")
                return True

        print(f"Error: {str(db_name)} not found. Creating DB...")
        self.create_database(db_name)

    def populate_result_dictionary(self, data_field, cmd, iteration, date):

        body = self.measurement_templatedic.copy()
        body["fields"] = data_field
        body.pop("time")  # at the moment we use the db update time
        body["measurement"] = cmd
        body["tags"]["board"] = self.board
        body["tags"]["test_run"] = iteration
        return body

    # jsonifies a table like ps, netstat, etc, where the 1st row shows the keys
    def process_table(self, datain, cmd, iteration, date, mode="join"):
        keys = datain[0].split()
        for elem in datain[1:]:
            length = elem.split()
            if len(keys) <= len(length):
                if mode == "join":
                    length[len(keys) - 1 :] = [" ".join(length[len(keys) - 1 :])]
                elif mode == "drop":
                    length = length[: len(keys)]
            else:
                for _ in range(len(length), len(keys)):
                    length.append("null")
            res_dict = dict(list(zip(keys, length)))
            res_dict["date"] = date
            body = self.populate_result_dictionary(res_dict, cmd, iteration, date)
            self.db_data.append(body)
            print(
                "process_table: body: %s DB updating: %r"
                % (json.dumps(body, indent=4), self.write_points([body]))
            )
        self.db_data = []

    def send_to_db(self, datain, cmd, iteration, date):
        """
        whith this function we can send data to the db in "realtime"
        i.e. we run a command like ps on the station, and the results
        can be posted immediately
        """
        # the mode allows to either join or drop the trailing columns
        # i.e. in ps the command has 5 cloumns (PID, user, etc), and
        # the las column can have trailing values (the actual command)
        mode = "join"
        # just get the part of the command up to the |
        command = cmd[: cmd.index("|")] if "|" in cmd else cmd

        self.process_table(datain, command, iteration, date, mode)

    def log_data(self, value):
        iperf_data = []
        for idx_dict in value:
            idx = idx_dict.copy()
            if "iperf" in idx["service"]:
                for i in idx["data"]:
                    if idx["fields"] is None or i["value"] is None:
                        continue
                    data_unit = {"measurement": "throughput", "tags": {}}
                    data_unit["tags"]["board"] = self.board
                    data_unit["tags"]["test_run"] = self.test_run
                    data_unit["tags"]["service"] = idx["service"]
                    data_unit["tags"]["mode"] = idx["mode"]
                    data_unit["tags"]["flow"] = idx["flow"]
                    data_unit["tags"]["device"] = idx["device"].split("-")[0]
                    data_unit["tags"]["port"] = str(idx["port"])
                    data_unit["fields"] = {}

                    # being cheeky and adding port and protocol as we want
                    # them "selectable" (only fields can be selectable)
                    idx["fields"].extend(["port_value", "protocol_value"])
                    i["value"].extend([str(idx["port"]), str(idx["protocol"])])

                    data_unit["fields"] = dict(list(zip(idx["fields"], i["value"])))
                    data_unit["time"] = datetimetostr(
                        idx["timestamp"] + timedelta(seconds=float(i["value"][0]))
                    )
                    iperf_data.append(data_unit)
            else:
                data_unit = {"measurement": "response", "tags": {}}
                data_unit["tags"]["board"] = self.board
                data_unit["tags"]["test_run"] = self.test_run
                data_unit["tags"]["service"] = idx["service"]
                data_unit["fields"] = {}
                data_unit["fields"] = dict(list(zip(idx["fields"], idx["value"])))
                data_unit["time"] = datetimetostr(idx["timestamp"])
                iperf_data.append(data_unit)

        print(f"Update to DB : {self.write_points(iperf_data)!r}")

    def __setitem__(self, key, value):
        func_call = {"influx": self.log_data, "board": self.process_table}
        if key not in func_call:
            print(f"Key Error: {key} not found")
        else:
            func_call[key](value)
