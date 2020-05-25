import re
import sys

import pexpect
from boardfarm.devices import connection_decider, debian


class Macbook(debian.DebianBox):
    """Implementation for macbook."""

    model = "macbook"
    name = "mac_sniffer"
    prompt = [r".*\$"]
    iface_wifi = "en0"

    def __init__(self, *args, **kwargs):
        """Instance initialisation."""
        self.args = args
        self.kwargs = kwargs
        self.ipaddr = self.kwargs["ipaddr"]
        self.username = self.kwargs["username"]
        self.password = self.kwargs["password"]

        conn_cmd = 'ssh -o "StrictHostKeyChecking no" %s@%s' % (
            self.username,
            self.ipaddr,
        )

        self.connection = connection_decider.connection("local_cmd",
                                                        device=self,
                                                        conn_cmd=conn_cmd)
        self.connection.connect()

        if 0 == self.expect(["Password:"] + self.prompt):
            self.sendline(self.password)
            self.expect(self.prompt)

        # Hide login prints, resume after that's done
        self.logfile_read = sys.stdout

    def __str__(self):
        """Return string format.

        :return: MacBook
        :rtype: string
        """
        return "MacBook"

    def change_channel(self, channel):
        """Change channel via airport.

        :param channel: channel number
        :type channel: string
        """
        command = "airport --ch={}".format(channel)

        self.sudo_sendline(command)
        self.expect(self.prompt)
        self.expect(pexpect.TIMEOUT, timeout=5)

    def set_sniff_channel(self, channel):
        """Set sniff channel.

        :rtype: string
        """
        command = "airport %s sniff %s" % (self.iface_wifi, channel)
        self.sendline(command)
        self.expect(pexpect.TIMEOUT, timeout=3)
        self.sendline("\x03")
        self.expect(self.prompt)

    def wifi_scan(self):
        """Scan the SSIDs.

        :return: List of SSID
        :rtype: string
        """
        command = "airport %s --scan" % self.iface_wifi
        self.sendline(command)
        self.expect(pexpect.TIMEOUT, timeout=10)
        return self.before

    def wifi_check_ssid(self, ssid_name):
        """Check the SSID provided is present in the scan list.

        :param ssid_name: SSID name to be verified
        :type ssid_name: string
        :return: True or False
        :rtype: boolean
        """
        command = "airport %s --scan | grep %s" % (self.iface_wifi, ssid_name)
        self.sendline(command)
        self.expect(pexpect.TIMEOUT, timeout=10)
        tmp = re.sub(command, "", self.before)
        match = re.search(r"((\w.?)+)\s((\w+:)+)", tmp)
        if match.group(1) == ssid_name:
            return True
        else:
            return False

    def tcpdump_wifi_capture(self, capture_file="pkt_capture.pcap", count=10):
        """Capture wifi packet using tcpdump.

        :param command: tcpdump command to capture.
        :type command: String
        :param capture_file: Filename to create in which packets shall be stored. Defaults to 'pkt_capture.pcap'
        :type capture_file: String, Optional
        :return: Console ouput of tcpdump sendline command.
        :rtype: string
        """
        self.sendline("tcpdump -I -n -i %s -w %s -c %d" %
                      (self.iface_wifi, capture_file, count))
        self.expect(self.prompt)
        return self.before

    def tshark_wifi_read(self, capture_file, ssid_name="", opts=""):
        """Read the tcpdump packets and deletes the capture file after read.

        :param capture_file: Filename in which the packets were captured
        :type capture_file: String
        :param ssid_name: ssid name to filter. Defaults to ''
        :type ssid_name: String, Optional
        :param opts: can be more than one parameter but it should be joined with "and" eg: ('host '+dest_ip+' and port '+port). Defaults to ''
        :type opts: String, Optional
        :return: Output of tshark read command.
        :rtype: string
        """
        if opts == "":
            self.sendline('tshark -V -r %s wlan_mgt.ssid == "%s"' %
                          (capture_file, ssid_name))
        else:
            self.sendline('tshark -V -r %s "%s"' % (capture_file, opts))
        self.expect(pexpect.TIMEOUT, timeout=10)
        output = self.before
        self.sendline("rm %s" % (capture_file))
        self.expect(self.prompt)
        return output
