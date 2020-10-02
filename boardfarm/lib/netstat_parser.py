""" parse netstat command lines output into dataframes!
"""

import collections
from io import BytesIO

from pandas import DataFrame


class NetstatParser(object):
    """by default, linux netstat will list also the UNIX(IPC socket) family, which is too lengthy to show
    Hence only the activer internet connection ports are returned
    """

    def __init__(self, *options):
        """"""
        self.inet_connections = []

    def parse_inet_output_linux(self, output):
        """method to parse the netstat output"""
        sample_bytes = bytes(output, "utf-8")
        file_out = BytesIO(sample_bytes)
        value = file_out.readline()[:5].decode("utf-8")
        counter = 0
        while "Proto" not in value:
            header = file_out.readline()
            value = header[:5].decode("utf-8")
            counter += 1
            if counter == 20:
                raise Exception("Output has not been returned properly")
        val = file_out.readlines()
        for line in val:
            if "Active UNIX domain sockets" in str(line):
                break
            inet_header, result = self.parse_inet_connection_linux(line, header)
            if result:
                self.inet_connections.append(result)
        df = DataFrame(self.inet_connections, columns=inet_header)
        return df

    def parse_inet_connection_linux(self, line, header, sep=" "):
        """string.split(' ')  can not split fileds with multiple spaces between field -> filtering
        header of UNIX/inet family is fixed, a namedtuple is declared and return by parsing
        all decimal string is not cast into integer!!!
        unknown field is a single slash '-',  -> replaced by None,
        "*" means any IP/port in ascii format;  in numeric format:  0.0.0.0 means ANY IP address
        """
        line = line.decode("utf-8").split(sep)
        header = header.decode("utf-8").split(sep)
        fields = [
            it.replace("\r\n", "")
            for it in line
            if it != sep and it != "" and it != "\r\n"
        ]
        fields1 = [
            it1.replace("-", "")
            for it1 in header
            if it1 != " " and it1 != "" and it1 not in "\r\n"
        ]
        fields1 = [
            word for word in fields1 if word not in "Address" and word not in "name"
        ]
        dict_val = {}
        inet_header = []
        for val in fields1:
            if val == "Local":
                inet_header.append("LocalAddress")
                inet_header.append("LocalPort")
            elif val == "Foreign":
                inet_header.append("ForeignAddress")
                inet_header.append("ForeignPort")
            elif val == "PID/Program":
                inet_header.append("PID")
                inet_header.append("Program")
            else:
                inet_header.append(val)
        inet_connection = collections.namedtuple("inet_connection", inet_header)
        try:
            if len(fields) < 1:
                return
            for idx in range(len(fields1)):
                if fields1[idx] == "Local" or fields1[idx] == "Foreign":
                    portpos = fields[idx].rfind(":")
                    dict_val[fields1[idx] + "Address"] = fields[idx][:portpos]
                    dict_val[fields1[idx] + "Port"] = fields[idx][portpos + 1 :]
                elif fields[0].upper() == "UDP" and fields1[idx] == "State":
                    dict_val["State"] = ""
                elif "PID" in fields1[idx]:
                    if fields[0].upper() == "UDP":
                        idx = idx - 1
                    dict_val["PID"], dict_val["Program"] = fields[idx].split("/")
                else:
                    dict_val[fields1[idx].replace("-", "")] = fields[idx]
            return inet_header, inet_connection(**dict_val)
        except Exception:
            raise Exception(f"Problem in parsing the output for the line {line}!!!")
