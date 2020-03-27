# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
"""
Libraries to install linux packages
"""

import re
import warnings

import pexpect
from debtcollector import deprecate
from retry.api import retry_call

warnings.simplefilter('always', UserWarning)


def apt_install(device, name, timeout=120):
    """Install a package using apt-get

    :param device: Object of DebianBox
    :type device: Instance (ex: lan or wan instance)
    :param name: name of the package to install
    :type name: string
    :param timeout: timeout for expect, defaults to '120'
    :type timeout: integer, optional
    :raises assertion: package is not installed correctly
    """
    def _kill_stale_apt():
        pids = device.check_output("pgrep apt")
        if pids:
            print(
                "Stale apt PIDs identified!! - {}\nKilling them before installation"
                .format(pids.splitlines()))
            device.check_output("pkill apt")

    _kill_stale_apt()
    for _ in range(2):
        device.sendline('export DEBIAN_FRONTEND=noninteractive')
        device.expect(device.prompt)
        apt_update(device)
        device.sendline('apt-get install -q -y %s' % name)
        device.expect('Reading package')
        try:
            device.expect(device.prompt, timeout=timeout)
        except pexpect.TIMEOUT:
            device.sendcontrol('c')
            device.expect(pexpect.TIMEOUT, timeout=1)
            _kill_stale_apt()
            raise

        if "Could not get lock" in device.before:
            lock = re.findall("Could not get lock ([^\s]+)", device.before)
            pid = device.check_output("fuser -k {}".format(lock))
            pid = pid.replace("{}:".format(lock), "").strip()
            device.check_output("kill -9 {}".format(pid))
            print("Retrying apt installation, after releasing {} lock!".format(
                lock))
        else:
            break

    device.sendline('dpkg -l %s' % name)
    expect_string = 'dpkg -l %s' % name
    device.expect_exact(expect_string[-60:])
    i = device.expect(['dpkg-query: no packages found'] + device.prompt)
    assert (i != 0)


def apt_update(device, timeout=120):
    """Update the package database with apt-get

    :param device: Object of DebianBox
    :type device: Instance (ex: lan or wan instance)
    :param timeout: timeout for expect, defaults to '120'
    :type timeout: integer, optional
    """
    device.sendline('apt-get -q update')
    device.expect('Reading package')
    device.expect(device.prompt, timeout=timeout)


def install_iperf(device):
    """Install iPerf benchmark tool if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\niperf -v')
    try:
        device.expect('iperf version', timeout=10)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline(
            'apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install iperf'
        )
        device.expect(device.prompt, timeout=60)


def install_iperf3(device):
    """Install iPerf version3 benchmark tool if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\niperf3 -v')
    try:
        device.expect('iperf 3', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline(
            'apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install iperf3'
        )
        device.expect(device.prompt, timeout=60)


def install_tcpick(device):
    """Install tcpick if not present.
    tcpick - tcp stream sniffer and connection tracker

    :param device: lan or wan
    :type device: Object
    :raises assertion: tcpick installation failed
    """
    device.sendline('\ntcpick --version')
    try:
        device.expect('tcpick 0.2', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'tcpick')


def install_upnp(device):
    """Install miniupnpc  if not present.
    MiniUPnPc is a client library, enabling applications to access the services provided by an UPnP "Internet Gateway Device" present on the network

    :param device: lan or wan
    :type device: Object
    :raises assertion: upnp installation failed
    """
    device.sendline('\nupnpc --version')
    try:
        device.expect('upnpc : miniupnpc', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'miniupnpc')


def install_lighttpd(device):
    """Install lighttpd web server if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\nlighttpd -v')
    try:
        device.expect('lighttpd/1', timeout=8)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'lighttpd')


def install_netperf(device):
    """Install netperf benchmark tool if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\nnetperf -V')
    try:
        device.expect('Netperf version 2.4', timeout=10)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline(
            'apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install netperf'
        )
        device.expect(device.prompt, timeout=60)
    device.sendline('/etc/init.d/netperf restart')
    device.expect('Restarting')
    device.expect(device.prompt)


def install_endpoint(device):
    """Install endpoint(Performance Endpoint for Linux from Ixia) if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\npgrep endpoint')
    try:
        device.expect('pgrep endpoint')
        device.expect('[0-9]+\r\n', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline(
            'wget http://downloads.ixiacom.com/products/ixchariot/endpoint_library/8.00/pelinux_amd64_80.tar.gz'
        )
        device.expect(device.prompt, timeout=120)
        device.sendline('tar xvzf pelinux_amd64_80.tar.gz')
        device.expect('endpoint.install', timeout=90)
        device.expect(device.prompt, timeout=60)
        device.sendline('./endpoint.install accept_license')
        device.expect('Installation of endpoint was successful.', timeout=90)
        device.expect(device.prompt, timeout=60)


def install_hping3(device):
    """Install hping3 if not present.
    hping is a command-line oriented TCP/IP packet assembler/analyzer.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\nhping3 --version')
    try:
        device.expect('hping3 version', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        apt_install(device, 'hping3')


def install_python(device):
    """Install python if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\npython --version')
    try:
        device.expect('Python 2', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline(
            'apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install python-pip python-mysqldb'
        )
        device.expect(device.prompt, timeout=60)


def install_java(device):
    """Install java if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\njavac -version')
    try:
        device.expect('javac 1.8', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline(
            'echo "deb http://ppa.launchpad.net/webupd8team/java/ubuntu xenial main" | tee /etc/apt/sources.list.d/webupd8team-java.list'
        )
        device.expect(device.prompt)
        device.sendline(
            'echo "deb-src http://ppa.launchpad.net/webupd8team/java/ubuntu xenial main" | tee -a /etc/apt/sources.list.d/webupd8team-java.list'
        )
        device.expect(device.prompt)
        device.sendline(
            'apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys EEA14886'
        )
        device.expect(device.prompt)
        device.sendline('apt-get update -y')
        device.expect(device.prompt)
        deprecate(
            "Using apt install in sendline is deprecated! Please use apt_install",
            removal_version="> 1.1.1",
            category=UserWarning)
        device.sendline('apt-get install oracle-java8-installer -y')
        device.expect_exact(
            "Do you accept the Oracle Binary Code license terms")
        device.sendline('yes')
        device.expect(device.prompt, timeout=60)
        device.sendline('\njavac -version')
        try:
            device.expect('javac 1.8', timeout=5)
            device.expect(device.prompt)
        except:
            device.sendline(
                'sed -i \'s|JAVA_VERSION=8u144|JAVA_VERSION=8u152|\' /var/lib/dpkg/info/oracle-java8-installer.*'
            )
            device.sendline(
                'sed -i \'s|PARTNER_URL=http://download.oracle.com/otn-pub/java/jdk/8u144-b01/090f390dda5b47b9b721c7dfaa008135/|PARTNER_URL=http://download.oracle.com/otn-pub/java/jdk/8u152-b16/aa0333dd3019491ca4f6ddbe78cdb6d0/|\' /var/lib/dpkg/info/oracle-java8-installer.*'
            )
            device.sendline(
                'sed -i \'s|SHA256SUM_TGZ="e8a341ce566f32c3d06f6d0f0eeea9a0f434f538d22af949ae58bc86f2eeaae4"|SHA256SUM_TGZ="218b3b340c3f6d05d940b817d0270dfe0cfd657a636bad074dcabe0c111961bf"|\' /var/lib/dpkg/info/oracle-java8-installer.*'
            )
            device.sendline(
                'sed -i \'s|J_DIR=jdk1.8.0_144|J_DIR=jdk1.8.0_152|\' /var/lib/dpkg/info/oracle-java8-installer.*'
            )
            deprecate(
                "Using apt install in sendline is deprecated! Please use apt_install",
                removal_version="> 1.1.1",
                category=UserWarning)
            device.sendline('apt-get install oracle-java8-installer -y')
            device.expect(device.prompt, timeout=60)


def install_telnet_server(device, remove=False):
    """Install xinetd/telnetd if not present.

    :param device: lan or wan
    :type device: Object
    :param remove: True or False, defaults to False
    :type remove: Boolean, optional
    :raises assertion: xinetd/telnetd installation failed
    """

    device.sendline('\nxinetd -version')
    if remove:
        device.expect(device.prompt)
        device.sendline("service xinetd stop")
        device.expect(device.prompt, timeout=10)
        device.sendline("/etc/init.d/xinetd status")
        device.expect(device.prompt, timeout=10)
        device.sendline('apt-get purge --auto-remove xinetd telnetd -y')
        device.expect(device.prompt, timeout=20)
        return
    try:
        device.expect('xinetd Version 2.3', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'xinetd')
    device.sendline('\ndpkg -l | grep telnetd')
    try:
        device.expect('telnet server', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'telnetd')
        device.sendline('echo \"service telnet\" > /etc/xinetd.d/telnet')
        device.sendline('echo "{" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"disable = no\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"flags = REUSE IPv6\" >> /etc/xinetd.d/telnet')
        device.sendline(
            'echo \"socket_type = stream\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"wait = no\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"user = root\" >> /etc/xinetd.d/telnet')
        device.sendline(
            'echo \"server = /usr/sbin/in.telnetd\" >> /etc/xinetd.d/telnet')
        device.sendline(
            'echo \"log_on_failure += USERID\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"}\" >> /etc/xinetd.d/telnet')
        device.expect(device.prompt, timeout=60)
        pty_num = len(
            device.check_output("cat /etc/securetty | grep pts/").split("\n"))
        # ensure 10 pts sessions for telnet server.
        for i in range(pty_num, 10):
            device.check_output('echo "pts/%s" >> /etc/securetty' % i)
    device.sendline("service xinetd restart")
    device.expect(['Starting internet superserver: xinetd.'], timeout=60)
    device.expect(device.prompt)
    assert "[ + ]  xinetd" in device.check_output("service --status-all")


def install_tcl(device):
    """Install tcl if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\necho \'puts $tcl_patchLevel\' | tclsh')
    try:
        device.expect('8.6', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'tcl')


def install_telnet_client(device):
    """Install telnet client if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\ndpkg -l | grep telnet')
    try:
        device.expect('telnet client', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'telnet')


def install_expect(device):
    """Install expect if not present.
    Expect is a tool for automating interactive applications

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\nexpect -version')
    try:
        device.expect('expect version 5', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'expect')


def install_wget(device):
    """Install wget if not present.
    Wget is a software package for retrieving files using HTTP, HTTPS, FTP and FTPS

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\nwget --version')
    try:
        device.expect('GNU Wget 1', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'wget')


def install_ftp(device):
    """Install ftp if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('apt-get update')
    device.expect(device.prompt, timeout=90)
    device.sendline('\ndpkg -l | grep ftp')
    try:
        device.expect('classical file transfer client', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'ftp')


def install_xampp(device):
    """Install xampp if not present.
    XAMPP is a cross-platform web server solution

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\n/opt/lampp/lampp --help')
    try:
        device.expect('Usage: lampp', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline(
            'wget https://www.apachefriends.org/xampp-files/5.6.20/xampp-linux-x64-5.6.20-0-installer.run'
        )
        device.expect(device.prompt)
        device.sendline('chmod +x xampp-linux-x64-5.6.20-0-installer.run')
        device.expect(device.prompt)
        device.sendline('./xampp-linux-x64-5.6.20-0-installer.run')
        device.expect_exact("XAMPP Developer Files")
        device.sendline('n')
        device.expect_exact("Is the selection above correct?")
        device.sendline('y')
        device.expect_exact("Press [Enter] to continue")
        device.sendline('')
        device.expect_exact("Do you want to continue?")
        device.sendline('y')
        device.expect(device.prompt, timeout=120)
        device.sendline('/opt/lampp/lampp restart')
        device.expect(device.prompt)
        device.sendline('touch /opt/lampp/htdocs/test.txt')
        device.expect(device.prompt, timeout=120)


def install_snmpd(device, post_cmd=None):
    """Install snmpd, use the 'post_cmd' to edit /etc/snmp/snmpd.conf
    (or for whatever is needed just after the installation)

    :param device: lan or wan
    :type device: Object
    :param post_cmd: linux command to add/delete/update/replace content
                      of a file related to snmpd, post installtion, defaults to None
    :type post_cmd: string, optional
    """
    apt_install(device, 'snmpd')
    # by default snmpd only listen to connections from localhost, comment it out
    device.sendline(
        "sed 's/agentAddress  udp:127.0.0.1:161/#agentAddress  udp:127.0.0.1:161/' -i /etc/snmp/snmpd.conf"
    )
    device.expect(device.prompt)

    if post_cmd:
        device.sendline(post_cmd)
        device.expect(device.prompt)
    device.sendline('service snmpd restart')
    device.expect(device.prompt)


def install_snmp(device):
    """Install snmp if not present.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('\nsnmpget --version')
    try:
        device.expect('NET-SNMP version:', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt update')
        device.expect(device.prompt)
        apt_install(device, 'snmp')


def install_vsftpd(device, remove=False):
    """Install vsftpd if not present.
    vsftpd is a FTP server for Unix-like systems, including Linux

    :param device: lan or wan
    :type device: Object
    :param remove: True or False, defaults to False
    :type remove: Boolean, optional
    """
    if not remove:
        device.sendline('apt-get update')
        device.expect(device.prompt, timeout=90)
        apt_install(device, 'vsftpd')
        device.sendline(
            'sed -i "s/pam_service_name=vsftpd/pam_service_name=ftp/g" /etc/vsftpd.conf'
        )
        device.expect(device.prompt, timeout=5)
        device.sendline(
            'sed -i "s/#write_enable=YES/write_enable=YES/g" /etc/vsftpd.conf')
        device.expect(device.prompt, timeout=5)
        device.sendline('service vsftpd restart')
        device.expect(device.prompt, timeout=60)
    else:
        '''Stopping the services running'''
        device.sendline("service vsftpd stop")
        device.expect(device.prompt, timeout=15)
        device.sendline("/etc/init.d/vsftpd status")
        device.expect(device.prompt, timeout=15)
        device.sendline('apt-get purge --auto-remove vsftpd -y')
        device.expect(device.prompt, timeout=30)


def install_pysnmp(device):
    """Install pysnmp if not present.
    Pysnmp is a pure-Python SNMP engine implementation

    :param device: lan or wan
    :type device: Object
    :raises assertion: Failed to install pysnmp library
    """
    install_flag = False
    for i in range(1, 3):
        try:
            device.sendline('\npip freeze | grep pysnmp')
            device.expect('pysnmp==', timeout=i * (5 * i))
            device.expect_prompt()
            install_flag = True
            break
        except:
            device.sendcontrol('c')
            device.expect_prompt()
            device.sendline('pip install -q pysnmp')
            device.expect_prompt(timeout=150)
            device.expect(pexpect.TIMEOUT, timeout=5)

    assert install_flag, "Failed to install pysnmp library"


def install_iw(device):
    """Install iw if not present.
    iw is nl80211 based CLI configuration utility for wireless devices

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('iw --version')
    try:
        device.expect('iw version', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'iw')


def install_jmeter(device):
    """Install jmeter if not present.
    JMeter is an Apache project, used as a load testing tool for analyzing and
    measuring the performance of a variety of services, with a focus on web applications

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('export PATH=$PATH:/opt/apache-jmeter-5.1.1/bin/')
    device.expect(device.prompt)
    device.sendline('jmeter --version')
    try:
        device.expect_exact('The Apache Software Foundation')
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'wget')
        apt_install(device, 'openjdk-8-jre-headless')
        device.sendline(
            'wget https://www-us.apache.org/dist//jmeter/binaries/apache-jmeter-5.1.1.tgz'
        )
        device.expect(device.prompt, timeout=90)
        device.sendline('tar -C /opt -zxf apache-jmeter-5.1.1.tgz')
        device.expect(device.prompt, timeout=120)
        device.sendline('rm apache-jmeter-*')


def install_IRCserver(device):
    """Install irc server if not present.
    Internet Relay Chat (IRC) is an application layer protocol
    that facilitates communication in the form of text.
    The chat process works on a client/server model.

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('inspircd --version')
    try:
        device.expect('InspIRCd-', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'update-inetd')
        apt_install(device, 'inspircd')


def install_dovecot(device, remove=False):
    """Un/Install dovecot server if not present.
    Dovecot is an open source IMAP and POP3 server for Unix-like operating systems.

    :param device: lan or wan
    :type device: Object
    :param remove: True or False, defaults to False
    :type remove: Boolean, optional
    :raises assertion: Failed to install dovecot
    """
    if remove:
        device.check_output(
            "killall dovecot; service dovecot stop; apt purge -y --auto-remove dovecot-*"
        )
        device.check_output("rm -rf /etc/dovecot")
        return
    device.sendline('dovecot --version')
    try:
        device.expect(' \(', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect_prompt()
        apt_install(device, 'update-inetd')
        apt_install(device, 'dovecot-imapd dovecot-pop3d -y')
        device.check_output("cd /usr/share/dovecot; ./mkcert.sh; cd")
        ssl_settings = [
            "ssl = yes", "ssl_cert = </etc/dovecot/dovecot.pem",
            "ssl_key = </etc/dovecot/private/dovecot.pem"
        ]
        device.sendline(
            "cat > /etc/dovecot/conf.d/10-ssl.conf << EOF\n%s\nEOF\n" %
            "\n".join(ssl_settings))
        device.expect_prompt()
        device.check_output("service dovecot restart")
        assert "dovecot is running" in device.check_output(
            "service dovecot status"), "Failed to install dovecot"


def install_ovpn_server(device, remove=False, _user='lan', _ip="ipv4"):
    """Un/Install the OpenVPN server via a handy script
    OpenVPN implements virtual private network techniques to create secure point-to-point or site-to-site connections

    :param device: lan or wan
    :type device: Object
    :param remove: True or False, defaults to False
    :type remove: Boolean, optional
    :param _user: lan or wan, defaults to lan
    :type _user: String, optional
    :param _ip: ipv4 or ipv6, defaults to ipv4
    :type _ip: string, optional
    """
    device.sendline('cd')
    device.expect_exact('cd')
    device.expect(device.prompt)

    # This is where the original setup script comes from. For conveninence we shall
    # copy the version commited in test/lib/scripts to the server (we cannot always
    # guarantee tha the containers will have web access)
    #device.sendline('curl -O https://raw.githubusercontent.com/Angristan/openvpn-install/master/openvpn-install.sh')
    import os
    ovpn_install_script = 'openvpn-install.sh'
    fname = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         'scripts/' + ovpn_install_script)
    dest = '/root/' + ovpn_install_script
    device.copy_file_to_server(fname, dest)
    device.sendline('chmod +x openvpn-install.sh')
    device.expect(device.prompt)

    device.sendline('ls -l /etc/init.d/openvpn')
    index = device.expect([
        '(\\sroot\\sroot\\s{1,}\\d{4}(.*)\\s{1,}\\/etc\\/init\\.d\\/openvpn)'
    ] + ['No such file or directory'])
    device.expect(device.prompt)

    # do we want to remove it?
    if remove:
        if index == 0:
            # be brutal, the server may not be responding to a stop
            device.sendline('killall -9 openvpn')
            device.expect(device.prompt, timeout=60)
            device.sendline('./openvpn-install.sh')
            device.expect('Select an option.*: ')
            device.sendline('3')
            device.expect_exact(
                'Do you really want to remove OpenVPN? [y/n]: n')
            device.sendcontrol('h')
            device.sendline('y')
            device.expect(device.prompt, timeout=90)
        return

    # do the install
    if index != 0:
        device.sendline('rm -f /etc/openvpn/server.conf')
        device.expect(device.prompt)
        dev_ip = device.get_interface_ipaddr(device.iface_dut)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        shim = getattr(device, "shim", None)
        output = shim if shim else ""
        device.sendline('%s ./openvpn-install.sh' % output)
        device.expect('IP address:.*', timeout=120)
        for i in range(20):
            device.sendcontrol('h')
        device.sendline(str(dev_ip))
        device.expect('Public IPv4 address or hostname:.*')
        device.sendline(dev_ip)
        device.expect('Do you want to enable IPv6 support.*:.*')
        if _ip == "ipv4":
            device.sendline()
        elif _ip == "ipv6":
            device.sendcontrol('h')
            device.sendline('y')
        device.expect('Port choice.*:.*')
        device.sendline()
        device.expect('Protocol.*:.*')
        device.sendline()
        device.expect('DNS.*:.*')
        device.sendline()
        device.expect('Enable compression.*:.*')
        device.sendline()
        device.expect('Customize encryption settings.*: n')
        device.sendline()
        device.expect('Press any key to continue...')
        device.sendline()
        device.expect('.*Client name: ', timeout=120)
        device.sendline(_user)
        device.expect('Select an option.*: 1')
        device.sendline()
        device.expect(device.prompt, timeout=90)
        device.sendline('/etc/init.d/openvpn stop')
        device.expect(device.prompt)
        if _ip == "ipv4":
            # only add it in ipv4
            device.sendline('echo "local ' + dev_ip +
                            '" > /etc/openvpn/server.conf.tmp')
            device.expect(device.prompt)
            device.sendline(
                'cat /etc/openvpn/server.conf >> /etc/openvpn/server.conf.tmp')
            device.expect(device.prompt)
            device.sendline(
                'mv /etc/openvpn/server.conf.tmp /etc/openvpn/server.conf')
            device.expect(device.prompt)

    device.sendline('/etc/init.d/openvpn status')
    index = device.expect(["VPN 'server' is running"] +
                          ["VPN 'server' is not running ... failed"] +
                          device.prompt,
                          timeout=90)
    if index != 0:
        device.sendline('/etc/init.d/openvpn restart')
        device.expect(["Starting virtual private network daemon: server"])
        # the following are for diagnositcs
        device.sendline('/etc/init.d/openvpn status')
        device.expect(device.prompt)
        device.sendline('ip a')

    device.expect(device.prompt)


def install_ovpn_client(device, remove=False):
    """Un/Install the OpenVPN client
    OpenVPN implements virtual private network techniques to create secure point-to-point or site-to-site connections

    To run the client as a daemon use:
    openvpn --daemon vpn   --log ovpn.log --config ./<user>.ovpn
    :param device: lan or wan
    :type device: Object
    :param remove: True or False, defaults to False
    :type remove: Boolean, optional
    """
    if remove:
        device.sendline('killall -9 openvpn')
        device.expect(device.prompt)
        device.sendline('apt purge --auto-remove openvpn -y')
        device.expect(device.prompt, timeout=120)
        return

    device.sendline('apt-get update')
    device.expect(device.prompt)
    apt_install(device, 'openvpn')


def install_pptpd_server(device, remove=False):
    """Un/Install the pptpd
    pptpd is the Poptop PPTP daemon, which manages tunnelled PPP connections encapsulated in GRE using the PPTP VPN protocol

    :param device: lan or wan
    :type device: Object
    :param remove: True or False, defaults to False
    :type remove: Boolean, optional
    """
    import pexpect
    device.expect([pexpect.TIMEOUT] + device.prompt, timeout=5)
    device.sendline('ls -l /usr/sbin/pptpd')
    index = device.expect(
        ['(\\s{1,}\\d{4}()\\s{1,}\\/etc\\/init\\.d\\/openvpn)'] +
        device.prompt,
        timeout=90)
    if remove:
        if index == 0:
            device.sendline("/etc/init.d/pptpd stop")
            device.expect(device.prompt, timeout=60)
            device.sendline("apt-get purge --auto-remove pptpd -y")
            device.expect(device.prompt, timeout=60)
        return

    if index != 0:
        apt_install(device, 'pptpd')

    device.sendline("/etc/init.d/pptpd restart")
    device.expect(device.prompt, timeout=60)


def install_pptp_client(device, remove=False):
    """Un/Install the pptp-linux package
    pptpd is the Poptop PPTP daemon, which manages tunnelled PPP connections encapsulated in GRE using the PPTP VPN protocol

    :param device: lan or wan
    :type device: Object
    :param remove: True or False, defaults to False
    :type remove: Boolean, optional
    """
    device.sendline('pptp --version')
    index = device.expect(['pptp version'] + device.prompt, timeout=90)

    if remove:
        if index == 0:
            device.expect(device.prompt)
            device.sendline("poff pptpserver")
            device.expect(device.prompt)
            device.sendline('apt-get purge --auto-remove pptp-linux -y')
            device.expect(device.prompt, timeout=60)
        return

    if index != 0:
        apt_install(device, 'pptp-linux')


def install_postfix(device):
    """Install postfix server if not present.
    Postfix is a free and open-source mail transfer agent that routes and delivers electronic mail.

    :param device: lan or wan
    :type device: Object
    :raises assertion: 1. Errors Encountered during installation. Installaion failed
                       2. System mail name option is not received. Installaion failed
                       3. Unable to start Postfix service.Service is not properly installed
    """
    device.sendline("apt-get purge postfix -y")
    device.expect(device.prompt, timeout=40)
    device.sendline('postconf -d | grep mail_version')
    try:
        device.expect('mail_version =', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')  # Update inetd before installation
        if 0 == device.expect(['Reading package', pexpect.TIMEOUT],
                              timeout=60):
            device.expect(device.prompt, timeout=300)
        else:
            print("Failed to download packages, things might not work")
            for i in range(3):
                device.sendcontrol('c')
                device.expect(device.prompt, timeout=10)
            device.sendline("cat /etc/resolv.conf")
            device.expect(device.prompt)
            raise Exception(
                "Failed to download packages, things might not work")
        deprecate(
            "Using apt install in sendline is deprecated! Please use apt_install",
            removal_version="> 1.1.1",
            category=UserWarning)
        device.sendline("apt-get install postfix -y")
        install_settings = device.expect(
            ['General type of mail configuration:'] +
            ['Errors were encountered'] + device.prompt,
            timeout=120)
        print(install_settings)
        if install_settings == 0:
            device.sendline("2")
            assert 0 == device.expect(
                ['System mail name:'] + device.prompt, timeout=90
            ), "System mail name option is not received. Installaion failed"
            device.sendline("testingsmtp.com")
            assert 0 != device.expect(
                ['Errors were encountered'] + device.prompt,
                timeout=90), "Errors Encountered. Installaion failed"

        elif install_settings == 1:
            assert 0 != 1, "Errors Encountered. Installaion failed"

        elif install_settings == 2:
            device.sendline('postconf -d | grep mail_version')
            device.expect('mail_version =', timeout=5)

        device.sendline("service postfix start")
        assert 0 != device.expect(
            ['failed'] + device.prompt, timeout=90
        ), "Unable to start Postfix service.Service is not properly installed"


def check_pjsua(device):
    """Check if softphone is present.
    pjsua is a command line SIP user agent

    :param device: lan or wan
    :type device: Object
    """
    device.sendline('pjsua')
    i = device.expect(['Ready: Success'] + device.prompt, timeout=10)

    def recover_shell():
        device.sendcontrol('c')
        device.expect(device.prompt, timeout=10)

    retry_call(recover_shell, tries=5)

    if i == 0:
        return True
    else:
        return False


def install_pjsua(device,
                  url="https://www.pjsip.org/release/2.9/pjproject-2.9.tar.bz2"
                  ):
    """Install softphone if not present.
    pjsua is a command line SIP user agent

    :param device: lan or wan
    :type device: Object
    :param url: url to download pjsua package, defaults to "https://www.pjsip.org/release/2.9/pjproject-2.9.tar.bz2"
    :type url: String, optional
    :raises assertion: 1. Unable to find executable
                       2. Unable to start Pjsua.Service is not installed
    """
    result = check_pjsua(device)
    if not result:
        apt_install(device, 'make')
        apt_install(device, 'gcc')
        apt_install(device, 'pkg-config')
        apt_install(device, 'libasound2-dev')
        install_wget(device)
        device.sendline('wget %s' % url)
        device.expect(device.prompt, timeout=100)
        device.sendline('tar -xjf %s' % url.split("/")[-1])
        device.expect(device.prompt, timeout=70)
        device.sendline('rm %s' % url.split("/")[-1])
        device.expect(device.prompt, timeout=60)
        device.sendline("ls")
        device.expect(device.prompt)
        folder_name = re.findall('(pjproject\-[\d\.]*)\s', device.before)[0]
        device.sendline('cd %s' % folder_name)
        device.expect(device.prompt)
        device.sendline(
            './configure && make dep && make && make clean &&  make install 2>&1 & '
        )
        # this takes more than 4 mins to install
        device.expect(pexpect.TIMEOUT, timeout=400)
        device.expect(device.prompt)
        device.sendline('ls pjsip-apps/bin/pjsua-x86_64-unknown-linux-gnu')
        assert 0 == device.expect(
            ['pjsip-apps/bin/pjsua-x86_64-unknown-linux-gnu'] +
            device.prompt), "Unable to find executable"
        device.expect(device.prompt)
        device.sendline(
            'cp pjsip-apps/bin/pjsua-x86_64-unknown-linux-gnu /usr/local/bin/pjsua'
        )
        device.expect(device.prompt)
        result = check_pjsua(device)
        assert 0 != result, "Unable to start Pjsua.Service is not installed."


def configure_IRCserver(device, user_name):
    """To modify and configure IRC server.

    :param device: lan or wan
    :type device: Object
    :param user_name: User name for admin nick name, operator name
    :type user_name: String
    :raises assertion: 1. Start Service inspircd failed
                       2. Service inspircd is not running
    """

    device.sendline(
        "rm /etc/inspircd/inspircd.conf; touch /etc/inspircd/inspircd.conf")
    device.expect(device.prompt)

    device.sendline('''cat > /etc/inspircd/inspircd.conf << EOF
<server name="irc.boardfarm.net"
        description="Boardfarm IRC Server"
        network="Boardfarm">

<admin name="Boardfarm"
        nick="%s"
        email="admin@irc.boardfarm.net">

<bind address="" port="6667" type="clients">

<power diepass="12345" restartpass="12345" pause="2">

<connect allow="*"
        timeout="60"
        flood="20"
        threshold="1"
        pingfreq="120"
        sendq="262144"
        recvq="8192"
        localmax="3"
        globalmax="3">

<class name="Shutdown"
        commands="DIE RESTART REHASH LOADMODULE UNLOADMODULE RELOAD">
<class name="ServerLink"
        commands="CONNECT SQUIT RCONNECT MKPASSWD MKSHA256">
<class name="BanControl"
        commands="KILL GLINE KLINE ZLINE QLINE ELINE">
<class name="OperChat"
        commands="WALLOPS GLOBOPS SETIDLE SPYLIST SPYNAMES">
<class name="HostCloak"
        commands="SETHOST SETIDENT SETNAME CHGHOST CHGIDENT">

<type name="NetAdmin"
        classes="OperChat BanControl HostCloak Shutdown ServerLink"
        host="netadmin.omega.org.za">
<type name="GlobalOp"
        classes="OperChat BanControl HostCloak ServerLink"
        host="ircop.omega.org.za">
<type name="Helper"
        classes="HostCloak"
        host="helper.omega.org.za">

<oper name="%s"
        password="12345"
        host="*@*"
        type="NetAdmin">

<files motd="/etc/inspircd/inspircd.motd"
        rules="/etc/inspircd/inspircd.rules">

<channels users="20"
        opers="60">

<dns server="127.0.0.1" timeout="5">

<pid file="/var/run/inspircd.pid">

<options prefixquit="Quit: "
        noservices="no"
        qaprefixes="no"
        deprotectself="no"
        deprotectothers="no"
        flatlinks="no"
        hideulines="no"
        syntaxhints="no"
        cyclehosts="yes"
        ircumsgprefix="no"
        announcets="yes"
        disablehmac="no"
        hostintopic="yes"
        quietbursts="yes"
        pingwarning="15"
        allowhalfop="yes"
        exemptchanops="">

<security hidewhois=""
        userstats="Pu"
        customversion=""
        hidesplits="no"
        hidebans="no"
        operspywhois="no"
        hidemodes="eI"
        maxtargets="20">

<performance nouserdns="no"
        maxwho="128"
        softlimit="1024"
        somaxconn="128"
        netbuffersize="10240">

<whowas groupsize="10"
        maxgroups="100000"
        maxkeep="3d">

<timesync enable="no" master="no">

<badnick nick="ChanServ" reason="Reserved For Services">
<badnick nick="NickServ" reason="Reserved For Services">
<badnick nick="OperServ" reason="Reserved For Services">
<badnick nick="MemoServ" reason="Reserved For Services">
EOF''' % (user_name, user_name))
    device.expect(device.prompt)

    device.sendline("rm /etc/default/inspircd; touch /etc/default/inspircd")
    device.expect(device.prompt)
    device.sendline("echo 'INSPIRCD_ENABLED=1' > /etc/default/inspircd")
    device.expect(device.prompt)

    device.sendline("service inspircd restart")
    index = device.expect(['Starting Inspircd... done.'] + device.prompt,
                          timeout=30)
    assert index == 0, "Start Service inspircd"
    device.expect(device.prompt)
    device.sendline("netstat -tulpn | grep -i inspircd")
    index = device.expect(['tcp6'] + device.prompt, timeout=30)
    assert index == 0, "Service inspircd running"
    device.expect(device.prompt)


def configure_IRCclient(device, user_name, irc_client_scriptname, client_id,
                        irc_server_ip, socket_type):
    """To create a python file in IRC client. The script shall be used to connect to server

    :param device: lan or wan
    :type device: Object
    :param user_name: IRC Client user name to be used to connect
    :type user_name: String
    :param irc_client_scriptname: python file name to be created. Eg: irc_client_1.py
    :type irc_client_scriptname: String
    :param client_id: client_id Eg: 1st client: 1, 2nd client: 2
    :type client_id: Integer
    :param irc_server_ip: server ip for client wants to connect
    :type irc_server_ip: String
    :param socket_type: socket connection type. "6" for ipv6 connection and "" for ipv4 connection
    :type socket_type: String
    """

    device.sendline("touch %s" % irc_client_scriptname)
    device.expect(device.prompt)
    device.sendline('''cat > %s << EOF
import socket
import time

addr = "%s"
input = """6667
%s%s
testinguser%s
test"""

# Parse input.
lines = input.split('\\n')

# Connect.
client = socket.socket(socket.AF_INET%s, socket.SOCK_STREAM)
client.connect((addr, int(lines[0])))

# Handshake.
client.send('NICK ' + lines[1] + '\\r\\n')
client.send('USER ' + lines[2] + ' 0 * :' + lines[3] + '\\r\\n')

time.sleep(15)
client.send('join #channel\\r\\n')

while True:
    data = client.recv(8192)
    print('Received Messages: '+data)
    if 2 == %s:
        validate_msg = "client1"
    else:
        validate_msg = "client2"
    if validate_msg in data:
        client.send(str.encode("PRIVMSG #channel : Yes, the clients are able to communicate\\n"))
        print("connection success")
        client.send('quit #channel\\r\\n')
    else:
        client.send(str.encode("PRIVMSG #channel : Hi, I am client%s\\n"))
EOF''' % (irc_client_scriptname, irc_server_ip, user_name, client_id,
          client_id, socket_type, client_id, client_id))
    device.expect(device.prompt)


def install_tcpdump(device):
    """Install tcpdump if not present.

    :param device: lan or wan or wlan
    :type device: Object
    """
    device.sudo_sendline('tcpdump --version')
    try:
        device.expect('tcpdump version', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'tcpdump')


def install_tshark(device):
    """Install tshark if not present.

    :param device: lan or wan or wlan...
    :type device: Object
    """
    device.sudo_sendline('tshark -v')
    try:
        device.expect('TShark (Wireshark)', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'tshark')
