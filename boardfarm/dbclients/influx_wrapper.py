import datetime
import re

import pexpect

from boardfarm.dbclients.influx_db_helper import Influx_DB_Logger


class GenericWrapper:
    def __init__(self, **kwargs):
        """
        Pass kwargs as {} (empty) to avoid creating a database in this CTOR
        This is can used when the DB is already created elsewhere and then
        self.logger is set manually by whatever created GenericWrapper.
        """
        if bool(kwargs):
            self.logger = Influx_DB_Logger(**kwargs)
            self.logger.debug = False
        else:
            self.logger = None

        self.iperf_server_data = None
        self.iperf_client_data = None

        # set data in Mbps
        self.units = {
            "bits": 1,
            "bytes": 8,
            "kbits": 1024 * 1,
            "kbytes": 1024 * 8,
            "mbits": 1024 * 1024 * 1,
            "mbytes": 1024 * 1024 * 8,
            "gbits": 1024 * 1024 * 1024 * 1,
            "gbytes": 1024 * 1024 * 1024 * 8,
        }

    def check_file(self, device, fname):
        device.sendline("ls " + fname)
        idx = device.expect(["No such file or directory", pexpect.TIMEOUT], timeout=2)
        if idx == 0:
            assert "file " + fname + " not found"
        device.expect(device.prompt)

    def stat_file_timestamp(self, device, fname):
        device.sendline('date +%Y%m%d%H%M%S%6N -d "$(stat -c %x "' + fname + '")"')
        device.expect("([0-9]{20})")
        timestamp = device.match.group(1)
        device.expect(device.prompt)
        timestamp = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%S%f")
        return timestamp

    def get_details_dict(self, device, fname):
        data_dict = {}
        self.check_file(device, fname)
        device.sendline(f"head -10 {fname}")
        device.expect(device.prompt, timeout=300)
        val = device.before
        data_dict["mode"] = "udp" if "datagram" in val or "Cwnd" in val else "tcp"
        data_dict["flow"] = fname.split("_")[1]
        data_dict["port"] = re.search(r"_(\d+)", fname).group(1)
        data_dict["logfile"] = fname
        data_dict["last_index"] = None
        data_dict["fields"] = None
        data_dict["tag"] = "server" if "Server" in val else "client"
        data_dict["service"] = "iperf"
        data_dict["device"] = "server" if "Server" in val else "client"
        data_dict["timestamp"] = self.stat_file_timestamp(device, fname)
        return data_dict

    def log_data(self):
        self.logger["influx"] = self.iperf_client_data
        self.logger["influx"] = self.iperf_server_data

    def log_iperf_to_db(self, server, client, server_data, client_data):
        self.collect_logs("server", server, server_data)
        self.collect_logs("client", client, client_data)
        self.log_data()

    def collect_logs(self, tag, device, iperf_data):
        if tag == "client":
            data_list = self.iperf_client_data = [iperf_data]
        elif tag == "server":
            data_list = self.iperf_server_data = [iperf_data]
        else:
            raise ValueError("Invalid tag value")

        for idx in range(len(data_list)):
            meta = None
            meta_dict = None
            if tag == "server":
                device.sendline(f"tail -750 {data_list[idx]['logfile']}")
                device.expect(device.prompt, timeout=300)
                meta = [
                    i.strip() for i in device.before.split("\n") if i.strip() != ""
                ][1:]
                meta_dict = data_list[idx]

            if tag == "client":
                device.sendline(f"tail -750 {data_list[idx]['logfile']}")
                device.expect(device.prompt, timeout=300)
                meta = [
                    i.strip() for i in device.before.split("\n") if i.strip() != ""
                ][1:]
                meta_dict = data_list[idx]

            meta_dict["data"] = []
            last_index = None
            if meta_dict["last_index"] in meta:
                meta = meta[meta.index(meta_dict["last_index"]) + 1 :]
            for i in meta:
                if "[ ID]" in i and meta_dict["fields"] is None:
                    meta_dict["fields"] = [j for j in i.split(" ") if j != ""][2:5]
                if i.startswith("[SUM]"):
                    last_index = i
                    temp = {}
                    line = [j for j in i.split(" ") if j != ""]
                    temp["type"] = (
                        "data"
                        if float(line[1].split("-")[1]) - float(line[1].split("-")[0])
                        < 2
                        else "result"
                    )
                    if line[4].lower() in self.units.keys():
                        temp["value"] = [
                            line[1].split("-")[1],
                            str(
                                round(
                                    float(line[3])
                                    * self.units[line[4].lower()]
                                    / self.units["mbits"],
                                    3,
                                )
                            ),
                            line[5],
                        ]
                        meta_dict["data"].append(temp)
            meta_dict["last_index"] = last_index

    def get_acs_data(self, response_time):
        data_dict = {
            "fields": ["Response time"],
            "value": [response_time],
            "service": "ACS",
            "timestamp": datetime.datetime.now(),
        }
        self.logger["influx"] = [data_dict]
