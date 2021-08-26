import datetime
import logging
import os
import re

import pexpect
from termcolor import colored

from boardfarm.dbclients.influx_db_helper import Influx_DB_Logger
from boardfarm.lib.regexlib import AllValidIpv6AddressesRegex, ValidIpv4AddressRegex


class GenericWrapper:
    def __init__(self, **kwargs):
        """
        Pass kwargs as {} (empty) to avoid creating a database in this CTOR
        This is can used when the DB is already created elsewhere and then
        self.logger is set manually by whatever created GenericWrapper.
        """
        if bool(kwargs):
            self.logger = Influx_DB_Logger(**kwargs)
            self.logger.debug = True
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

    def get_details_dict(self, device, fname):
        logger = logging.getLogger("bft")
        data_dict = {}
        val = device.check_output(f"head -10 {fname}")
        if "iperf3: error - unable to connect to server" in val:
            logger.warning(
                colored(
                    "Client could not connect to server",
                    color="yellow",
                    attrs=["bold"],
                )
            )
            return

        if "Time:" in val:
            timestamp = re.search(r"Time: (.*)\r", val).group(1)
            timestamp = datetime.datetime.strptime(
                timestamp, "%a, %d %b %Y %H:%M:%S %Z"
            )
        else:
            logger.warning(
                colored(
                    "Unable to find timestamp in result file. Either you missed to pass -V parameter OR unable to connect.",
                    color="yellow",
                    attrs=["bold"],
                )
            )
            return

        data_dict["mode"] = "udp" if "Datagrams" in val else "tcp"
        if "Connecting to host" in val:
            data_dict["port"] = re.search(
                r"Connecting to host (.*), port (\d+)\r", val
            ).group(2)
            data_dict["device"] = data_dict["tag"] = "client"
            data_dict["flow"] = "DS" if "Reverse mode" in val else "US"
        elif "Server listening on" in val:
            data_dict["port"] = re.search(r"(Server listening on (\d+)\r)", val).group(
                2
            )
            data_dict["device"] = data_dict["tag"] = "server"
            data_dict["flow"] = "see client"
        else:
            logger.warning(
                colored(
                    "Server not listening on any port OR Client could not connect to server",
                    color="yellow",
                    attrs=["bold"],
                )
            )
            return

        proto_dict = {ValidIpv4AddressRegex: "ipv4", AllValidIpv6AddressesRegex: "ipv6"}
        for k, v in proto_dict.items():
            match = re.search(f"local {k} port.*connected to {k}", val)
            if match:
                data_dict["protocol"] = v
                break
        else:
            data_dict["protocol"] = "unknown"

        data_dict["logfile"] = fname
        data_dict["last_index"] = None
        data_dict["fields"] = None
        data_dict["service"] = "iperf"
        data_dict["timestamp"] = timestamp
        return data_dict

    def log_data(self):
        self.logger["influx"] = self.iperf_client_data
        self.logger["influx"] = self.iperf_server_data

    def log_iperf_to_db(self, server, client, server_data, client_data):
        self.collect_logs("server", server, server_data)
        self.collect_logs("client", client, client_data)
        self.log_data()

    def _copy_file_locally(self, dev, fname, dir="/tmp/", prompt=r":.*(\$|#)"):
        command = (
            f"scp -o StrictHostKeyChecking=no -P {dev.port}"
            f" {dev.username}@{dev.ipaddr}:{fname} {dir}"
        )
        cli = pexpect.spawn("/bin/bash", echo=False)
        cli.sendline(command)
        cli.expect("assword:")
        cli.sendline(dev.password)
        cli.expect(prompt)

    def _get_data(self, device, data_list, idx):
        lines = int(device.check_output(f"cat {data_list[idx]['logfile']}|wc -l"))
        if lines < 2:
            # for small files we can work off the propmt
            startline = 1
            buf = ""
            while lines > 0:
                buf += device.check_output(
                    f"sed -n '{startline},{startline+10}p' {data_list[idx]['logfile']}"
                )
                lines -= 10
                startline += 10
        else:
            # for big files we copy them to /tmp and load them directly
            self._copy_file_locally(device, data_list[idx]["logfile"])
            with open(f'/tmp/{os.path.basename(data_list[idx]["logfile"])}') as f:
                buf = f.read()
        return [i.strip() for i in buf.split("\n") if i.strip() != ""][1:]

    def collect_logs(self, tag, device, iperf_data):
        if tag == "client":
            data_list = self.iperf_client_data = [iperf_data]
        elif tag == "server":
            data_list = self.iperf_server_data = [iperf_data]
        else:
            raise ValueError("Invalid tag value")

        for idx in range(len(data_list)):
            meta = self._get_data(device, data_list, idx)
            meta_dict = data_list[idx]
            meta_dict["data"] = []
            last_index = None
            if meta_dict["last_index"] in meta:
                meta = meta[meta.index(meta_dict["last_index"]) + 1 :]
            for i in meta:
                if "[ ID]" in i and meta_dict["fields"] is None:
                    meta_dict["fields"] = i.split()[2:5]
                if i.startswith("[SUM]"):
                    last_index = i
                    temp = {}
                    line = i.split()
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

    def get_response_data(self, response_time, service, timestamp=None):
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        data_dict = {
            "fields": ["Response time"],
            "value": [response_time],
            "service": service,
            "timestamp": timestamp,
        }
        self.logger["influx"] = [data_dict]
