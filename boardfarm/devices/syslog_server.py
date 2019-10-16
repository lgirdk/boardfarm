
import re
import time
import datetime

class SyslogServer(object):
    '''
    Linux based syslog server
    '''

    model = ('syslog')
    profile = {}

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        self.syslog_ip = self.kwargs['ipaddr']
        self.syslog_path = self.kwargs.get('syslog_path', '/var/log/BF/')

    def __str__(self):
        return "SyslogServer"

    def remove_syslog_via_ip(self, ip):
        '''
        Remove dut syslog on server

        This method is to remove the syslog from the server for the given IP

        Parameters: (string)IP address of the DUT
        '''

        command = "rm %s/log_%s" % (self.syslog_path, ip)
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.prompt)

    def get_syslog_via_ip(self, ip, n=10):
        '''
        Getting the syslog

        This method is to get the syslog from the server

        Parameters: (string)Ip address of the DUT
                    (int) Number of lines to be returned

        Returns: (string)Syslog messages
        '''

        command = "tail -n %s %slog_%s" % (n, self.syslog_path, ip)
        req = self.check_output(command)
        return req

    def check_syslog_time(self, ip, check_string):
        '''
        Check for syslog time

        This method is to get the syslog message time in server
        and the time in DUT for a particular check string

        Parameters: (string)IP address of the DUT
                    (string):Chcek string or message for which the time to be fetched

        Returns: (string) Time of the syslog message
        '''
        log = self.get_syslog_via_ip(ip)
        match = re.search(".*\s(\d+\:\d+\:\d+).*(%s).*" % check_string, log)
        time_log_msg = match.group(1)

        # Check syslog time from server
        x = time.strptime(time_log_msg, '%H:%M:%S')
        time_log_msg = datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min, seconds=x.tm_sec).total_seconds()

        return time_log_msg
