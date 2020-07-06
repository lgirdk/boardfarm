#!/usr/bin/env python3
"""Syslog server method."""
import datetime
import re
import sys
import time

from boardfarm.devices import connection_decider, debian


class SyslogServer(debian.DebianBox):
    """Linux based syslog server."""

    model = "syslog"
    name = "syslog_server"
    prompt = [r".*\@.*:.*\$"]

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        self.syslog_ip = self.kwargs["ipaddr"]
        self.syslog_path = self.kwargs.get("syslog_path", "/var/log/BF/")
        self.username = self.kwargs["username"]
        self.password = self.kwargs["password"]

        conn_cmd = 'ssh -o "StrictHostKeyChecking no" %s@%s' % (
            self.username,
            self.syslog_ip,
        )

        self.connection = connection_decider.connection("local_cmd",
                                                        device=self,
                                                        conn_cmd=conn_cmd)
        self.connection.connect()
        self.linesep = "\r"

        if 0 == self.expect(["assword: "] + self.prompt):
            self.sendline(self.password)
            self.expect(self.prompt)

        # Hide login prints, resume after that's done
        self.logfile_read = sys.stdout

    def __str__(self):
        """Return string format.

        :return: SyslogServer
        :rtype: string
        """
        return "SyslogServer"

    def remove_syslog_via_ip(self, ip):
        """Remove the syslog from the server for the given IP.

        :param ip: IP address of the DUT
        :type ip: string
        """
        command = "rm %s/log_%s" % (self.syslog_path, ip)
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.prompt)

    def get_syslog_via_ip(self, ip, n=10):
        """Get the syslog from the server.

        Getting the syslog
        :param ip: Ip address of the DUT
        :type ip: string
        :param n: Number of lines to be returned, defaults to 10
        :type n: Integer, optional
        :return: Syslog messages
        :rtype: string
        """
        command = "tail -n %s %slog_%s" % (n, self.syslog_path, ip)
        req = self.check_output(command)
        return req

    def check_syslog_time(self, ip, check_string):
        """Get the syslog message time in server\
        and the time in DUT for a particular check string.

        :param IP: IP address of the DUT
        :type IP: string
        :param check_string: Chcek string or message for which the time to be fetched
        :type check_string: string
        :return: Time of the syslog message
        :rtype: string
        """
        log = self.get_syslog_via_ip(ip)
        match = re.search(r".*\s(\d+\:\d+\:\d+).*(%s).*" % check_string, log)
        time_log_msg = match.group(1)

        # Check syslog time from server
        x = time.strptime(time_log_msg, "%H:%M:%S")
        time_log_msg = datetime.timedelta(hours=x.tm_hour,
                                          minutes=x.tm_min,
                                          seconds=x.tm_sec).total_seconds()

        return time_log_msg
