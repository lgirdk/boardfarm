""" Syslog server method
"""
import re
import time
import datetime


class SyslogServer(object):
    """Linux based syslog server
    """

    model = ('syslog')
    profile = {}

    def __init__(self, *args, **kwargs):
        """ Constructor method
        """
        self.args = args
        self.kwargs = kwargs

        self.syslog_ip = self.kwargs['ipaddr']
        self.syslog_path = self.kwargs.get('syslog_path', '/var/log/BF/')

    def __str__(self):
        """Return string format

        :return: SyslogServer
        :rtype: string
        """
        return "SyslogServer"

    def remove_syslog_via_ip(self, ip):
        """To remove the syslog from the server for the given IP

        :param ip: IP address of the DUT
        :type ip: string
        """

        command = "rm %s/log_%s" % (self.syslog_path, ip)
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.prompt)

    def get_syslog_via_ip(self, ip, n=10):
        """To get the syslog from the server
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
        """This method is to get the syslog message time in server
        and the time in DUT for a particular check string

        :param IP: IP address of the DUT
        :type IP: string
        :param check_string: Chcek string or message for which the time to be fetched
        :type check_string: string
        :return: Time of the syslog message
        :rtype: string
        """
        log = self.get_syslog_via_ip(ip)
        match = re.search(".*\s(\d+\:\d+\:\d+).*(%s).*" % check_string, log)
        time_log_msg = match.group(1)

        # Check syslog time from server
        x = time.strptime(time_log_msg, '%H:%M:%S')
        time_log_msg = datetime.timedelta(hours=x.tm_hour,
                                          minutes=x.tm_min,
                                          seconds=x.tm_sec).total_seconds()

        return time_log_msg
