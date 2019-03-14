# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

def apt_install(device, name, timeout=120):
    apt_update(device)
    device.sendline('apt-get install -q -y %s' % name)
    device.expect('Reading package')
    device.expect(device.prompt, timeout=timeout)
    device.sendline('dpkg -l %s' % name)
    device.expect_exact('dpkg -l %s' % name)
    i = device.expect(['dpkg-query: no packages found' ] + device.prompt)
    assert (i != 0)

def apt_update(device, timeout=120):
    device.sendline('apt-get update')
    device.expect('Reading package')
    device.expect(device.prompt, timeout=timeout)

def install_iperf(device):
    '''Install iPerf benchmark tool if not present.'''
    device.sendline('\niperf -v')
    try:
        device.expect('iperf version', timeout=10)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline('apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install iperf')
        device.expect(device.prompt, timeout=60)

def install_iperf3(device):
    '''Install iPerf benchmark tool if not present.'''
    device.sendline('\niperf3 -v')
    try:
        device.expect('iperf 3', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline('apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install iperf3')
        device.expect(device.prompt, timeout=60)

def install_tcpick(device):
    '''Install tcpick if not present.'''
    device.sendline('\ntcpick --version')
    try:
        device.expect('tcpick 0.2', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install tcpick -y')
        assert 0 == device.expect(['Setting up tcpick']+ device.prompt, timeout=60),"tcpick installation failed"
        device.expect(device.prompt)

def install_upnp(device):
    '''Install miniupnpc  if not present.'''
    device.sendline('\nupnpc --version')
    try:
        device.expect('upnpc : miniupnpc', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install miniupnpc -y')
        assert 0 == device.expect(['Setting up miniupnpc.*']+ device.prompt, timeout=60),"upnp installation failed"
        device.expect(device.prompt)

def install_lighttpd(device):
    '''Install lighttpd web server if not present.'''
    device.sendline('\nlighttpd -v')
    try:
        device.expect('lighttpd/1', timeout=8)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        apt_install(device, 'lighttpd')

def install_netperf(device):
    '''Install netperf benchmark tool if not present.'''
    device.sendline('\nnetperf -V')
    try:
        device.expect('Netperf version 2.4', timeout=10)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline('apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install netperf')
        device.expect(device.prompt, timeout=60)
    device.sendline('/etc/init.d/netperf restart')
    device.expect('Restarting')
    device.expect(device.prompt)

def install_endpoint(device):
    '''Install endpoint if not present.'''
    device.sendline('\npgrep endpoint')
    try:
        device.expect('pgrep endpoint')
        device.expect('[0-9]+\r\n', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('wget http://downloads.ixiacom.com/products/ixchariot/endpoint_library/8.00/pelinux_amd64_80.tar.gz')
        device.expect(device.prompt, timeout=120)
        device.sendline('tar xvzf pelinux_amd64_80.tar.gz')
        device.expect('endpoint.install', timeout=90)
        device.expect(device.prompt, timeout=60)
        device.sendline('./endpoint.install accept_license')
        device.expect('Installation of endpoint was successful.', timeout=90)
        device.expect(device.prompt, timeout=60)

def install_hping3(device):
    '''Install hping3 if not present.'''
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
    '''Install python if not present.'''
    device.sendline('\npython --version')
    try:
        device.expect('Python 2', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline('apt-get -o DPkg::Options::="--force-confnew" -y --force-yes install python-pip python-mysqldb')
        device.expect(device.prompt, timeout=60)

def install_java(device):
    '''Install java if not present.'''
    device.sendline('\njavac -version')
    try:
        device.expect('javac 1.8', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('echo "deb http://ppa.launchpad.net/webupd8team/java/ubuntu xenial main" | tee /etc/apt/sources.list.d/webupd8team-java.list')
        device.expect(device.prompt)
        device.sendline('echo "deb-src http://ppa.launchpad.net/webupd8team/java/ubuntu xenial main" | tee -a /etc/apt/sources.list.d/webupd8team-java.list')
        device.expect(device.prompt)
        device.sendline('apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys EEA14886')
        device.expect(device.prompt)
        device.sendline('apt-get update -y')
        device.expect(device.prompt)
        device.sendline('apt-get install oracle-java8-installer -y')
        device.expect_exact("Do you accept the Oracle Binary Code license terms")
        device.sendline('yes')
        device.expect(device.prompt, timeout=60)
        device.sendline('\njavac -version')
        try:
            device.expect('javac 1.8', timeout=5)
            device.expect(device.prompt)
        except:
            device.sendline('sed -i \'s|JAVA_VERSION=8u144|JAVA_VERSION=8u152|\' /var/lib/dpkg/info/oracle-java8-installer.*')
            device.sendline('sed -i \'s|PARTNER_URL=http://download.oracle.com/otn-pub/java/jdk/8u144-b01/090f390dda5b47b9b721c7dfaa008135/|PARTNER_URL=http://download.oracle.com/otn-pub/java/jdk/8u152-b16/aa0333dd3019491ca4f6ddbe78cdb6d0/|\' /var/lib/dpkg/info/oracle-java8-installer.*')
            device.sendline('sed -i \'s|SHA256SUM_TGZ="e8a341ce566f32c3d06f6d0f0eeea9a0f434f538d22af949ae58bc86f2eeaae4"|SHA256SUM_TGZ="218b3b340c3f6d05d940b817d0270dfe0cfd657a636bad074dcabe0c111961bf"|\' /var/lib/dpkg/info/oracle-java8-installer.*')
            device.sendline('sed -i \'s|J_DIR=jdk1.8.0_144|J_DIR=jdk1.8.0_152|\' /var/lib/dpkg/info/oracle-java8-installer.*')
            device.sendline('apt-get install oracle-java8-installer -y')
            device.expect(device.prompt, timeout=60)

def install_telnet_server(device):
    '''Install xinetd/telnetd if not present.'''
    device.sendline('\nxinetd -version')
    try:
        device.expect('xinetd Version 2.3', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install xinetd -y')
        device.expect(device.prompt)
    device.sendline('\ndpkg -l | grep telnetd')
    try:
        device.expect('telnet server', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install telnetd -y')
        device.expect(device.prompt)
        device.sendline('echo \"service telnet\" > /etc/xinetd.d/telnet')
        device.sendline('echo "{" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"disable = no\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"flags = REUSE IPv6\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"socket_type = stream\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"wait = no\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"user = root\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"server = /usr/sbin/in.telnetd\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"log_on_failure += USERID\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"}\" >> /etc/xinetd.d/telnet')
        device.expect(device.prompt, timeout=60)

def install_tcl(device):
    '''Install tcl if not present.'''
    device.sendline('\necho \'puts $tcl_patchLevel\' | tclsh')
    try:
        device.expect('8.6', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install tcl -y')
        device.expect(device.prompt, timeout=60)

def install_telnet_client(device):
    '''Install telnet client if not present.'''
    device.sendline('\ndpkg -l | grep telnet')
    try:
        device.expect('telnet client', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install telnet -y')
        device.expect(device.prompt, timeout=60)

def install_expect(device):
    '''Install expect if not present.'''
    device.sendline('\nexpect -version')
    try:
        device.expect('expect version 5', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install expect -y')
        device.expect(device.prompt, timeout=60)

def install_wget(device):
    '''Install wget if not present.'''
    device.sendline('\nwget --version')
    try:
        device.expect('GNU Wget 1', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install wget -y')
        device.expect(device.prompt, timeout=60)

def install_ftp(device):
    '''Install ftp if not present.'''
    device.sendline('\ndpkg -l | grep ftp')
    try:
        device.expect('classical file transfer client', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install ftp -y')
        device.expect(device.prompt, timeout=60)

def install_xampp(device):
    '''Install xampp if not present.'''
    device.sendline('\n/opt/lampp/lampp --help')
    try:
        device.expect('Usage: lampp', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('wget https://www.apachefriends.org/xampp-files/5.6.20/xampp-linux-x64-5.6.20-0-installer.run')
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

def install_snmp(device):
    '''Install snmp if not present.'''
    device.sendline('\nsnmpget --version')
    try:
        device.expect('NET-SNMP version:', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install snmp -y')
        device.expect(device.prompt, timeout=60)

def install_vsftpd(device):
    '''Install vsftpd if not present.'''
    device.sendline('\nvsftpd -v')
    try:
        device.expect('vsftpd: version', timeout=10)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install vsftpd -y')
        device.expect(device.prompt, timeout=60)
    device.sendline('sed -i "s/pam_service_name=vsftpd/pam_service_name=ftp/g" /etc/vsftpd.conf')
    device.expect(device.prompt, timeout=5)
    device.sendline('sed -i "s/#write_enable=YES/write_enable=YES/g" /etc/vsftpd.conf')
    device.expect(device.prompt, timeout=5)
    device.sendline('service vsftpd restart')
    device.expect(device.prompt, timeout=60)

def install_pysnmp(device):
    '''Install pysnmp if not present.'''
    device.sendline('\npip freeze | grep pysnmp')
    try:
        device.expect('pysnmp==', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('pip install pysnmp')
        device.expect(device.prompt, timeout=90)

def install_iw(device):
    '''Install iw if not present.'''
    device.sendline('iw --version')
    try:
        device.expect('iw version', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install iw -y')
        device.expect(device.prompt, timeout=90)

def install_jmeter(device):
    '''Install jmeter if not present.'''
    device.sendline('export PATH=$PATH:/opt/apache-jmeter-5.0/bin/')
    device.expect(device.prompt)
    device.sendline('jmeter --version')
    try:
        device.expect_exact('The Apache Software Foundation')
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install  openjdk-8-jre-headless -y')
        device.expect(device.prompt, timeout=90)
        device.sendline('wget https://www-eu.apache.org/dist//jmeter/binaries/apache-jmeter-5.0.tgz')
        device.expect(device.prompt, timeout=90)
        device.sendline('tar -C /opt -zxf apache-jmeter-5.0.tgz')
        device.expect(device.prompt, timeout=120)
        device.sendline('rm apache-jmeter-5.0.tgz')

def install_IRCserver(device):
    '''Install irc server if not present.'''
    device.sendline('inspircd --version')
    try:
        device.expect('InspIRCd-', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install update-inetd -y') # Update inetd before installation
        device.expect(device.prompt, timeout=90)
        device.sendline('apt-get install inspircd -y')
        device.expect(['Setting up inspircd'], timeout=90)
        device.expect(device.prompt)

def install_dovecot(device):
    '''Install dovecot server if not present.'''
    device.sendline('dovecot --version')
    try:
        device.expect(' \(', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install update-inetd -y') # Update inetd before installation
        device.expect(device.prompt, timeout=90)
        device.sendline('apt-get install dovecot-imapd dovecot-pop3d -y')
        device.expect(['Processing triggers for dovecot-core'], timeout=90)
        device.expect(device.prompt)

def install_ovpn_server(device, remove=False, _user='lan', _ip="ipv4"):
    '''Un/Install the OpenVPN server via a handy script'''
    device.sendline('cd')
    device.expect_exact('cd')
    device.expect(device.prompt)

    # This is where the original setup script comes from. For conveninence we shall
    # copy the version commited in test/lib/scripts to the server (we cannot always
    # guarantee tha the containers will have web access)
    #device.sendline('curl -O https://raw.githubusercontent.com/Angristan/openvpn-install/master/openvpn-install.sh')
    import os
    ovpn_install_script = 'openvpn-install.sh'
    fname = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'scripts/'+ovpn_install_script)
    dest = '/root/'+ovpn_install_script
    device.copy_file_to_server(fname, dest)
    device.sendline('chmod +x openvpn-install.sh')
    device.expect(device.prompt)

    device.sendline('ls -l /etc/init.d/openvpn')
    index = device.expect(['(\\sroot\\sroot\\s{1,}\\d{4}(.*)\\s{1,}\\/etc\\/init\\.d\\/openvpn)'] + ['No such file or directory'])
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
            device.expect_exact('Do you really want to remove OpenVPN? [y/n]: n')
            device.sendcontrol('h')
            device.sendline('y')
            device.expect(device.prompt, timeout=90)
        return

    # do the install
    if index != 0:
        dev_ip = device.get_interface_ipaddr(device.iface_dut)
        device.sendline('apt-get update')
        device.expect(device.prompt)
        device.sendline('./openvpn-install.sh')
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
            addr = dev_ip
        elif _ip == "ipv6":
            addr = device.get_interface_ip6addr(device.iface_dut)
        device.sendline('echo "local '+addr+'" > /etc/openvpn/server.conf.tmp')
        device.expect(device.prompt)
        device.sendline('cat /etc/openvpn/server.conf >> /etc/openvpn/server.conf.tmp')
        device.expect(device.prompt)
        device.sendline('mv /etc/openvpn/server.conf.tmp /etc/openvpn/server.conf')
        device.expect(device.prompt)

    device.sendline('/etc/init.d/openvpn status')
    index = device.expect(["VPN 'server' is running" ] + [ "VPN 'server' is not running ... failed"] +device.prompt, timeout=90)
    if index != 0:
        device.sendline('/etc/init.d/openvpn restart')
        device.expect(["Starting virtual private network daemon: server" ])
        # the following are for diagnositcs
        device.sendline('/etc/init.d/openvpn status')
        device.expect(device.prompt)
        device.sendline('ip a')

    device.expect(device.prompt)

def install_ovpn_client(device, remove=False):
    '''
    Un/Install the OpenVPN client
    To run the client as a daemon use:
    openvpn --daemon vpn   --log ovpn.log --config ./<user>.ovpn
    '''
    if remove:
            device.sendline('killall -9 openvpn')
            device.expect(device.prompt)
            device.sendline('apt remove openvpn -y')
            device.expect(device.prompt, timeout=120)
            return

    device.sendline('apt-get install openvpn -y')
    device.expect(device.prompt, timeout=90)

def install_pptpd_server(device, remove=False):
    '''
    Un/Install the pptpd
    '''
    import pexpect
    device.expect([pexpect.TIMEOUT]+device.prompt, timeout=5)
    device.sendline('ls -l /usr/sbin/pptpd')
    index = device.expect(['(\\s{1,}\\d{4}()\\s{1,}\\/etc\\/init\\.d\\/openvpn)'] + device.prompt, timeout=90)
    if remove:
        if index == 0:
            device.sendline("/etc/init.d/pptpd stop")
            device.expect(device.prompt, timeout=60)
            device.sendline("apt-get remove pptpd -y")
            device.expect(device.prompt, timeout=60)
        return

    if index != 0:
        device.sendline("apt-get install pptpd -y")
        device.expect(device.prompt, timeout=90)

    device.sendline("/etc/init.d/pptpd restart")
    device.expect(device.prompt, timeout=60)

def install_pptp_client(device, remove=False):
    '''
    Un/Install the pptp-linux package
    '''
    device.sendline('pptp --version')
    index = device.expect(['pptp version'] + device.prompt, timeout=90)

    if remove:
        if index == 0:
            device.expect(device.prompt)
            device.sendline("poff pptpserver")
            device.expect(device.prompt)
            device.sendline('apt-get remove pptp-linux -y')
            device.expect(device.prompt, timeout=60)
        return

    if index != 0:
        device.sendline('apt-get install pptp-linux -y')

    device.expect(device.prompt, timeout=60)

def install_postfix(device):
    '''Install postfix server if not present.'''
    device.sendline('postconf -d | grep mail_version')
    try:
        device.expect('mail_version =', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get update') # Update inetd before installation
        device.expect(device.prompt, timeout=90)
        device.sendline("apt-get install postfix -y")
        install_settings = device.expect(['General type of mail configuration:'] + ['Errors were encountered'] + device.prompt, timeout = 120)
        print install_settings
        if install_settings ==0:
            device.sendline("2")
            assert 0 == device.expect(['System mail name:']+ device.prompt, timeout = 90), "System mail name option is note received. Installaion failed"
            device.sendline("testingsmtp.com")
            assert 0 != device.expect(['Errors were encountered']+ device.prompt, timeout = 90), "Errors Encountered. Installaion failed"

        elif install_settings ==1:
            assert 0 != 1, "Errors Encountered. Installaion failed"

        elif install_settings ==2:
            device.sendline('postconf -d | grep mail_version')
            device.expect('mail_version =', timeout=5)

        device.sendline("service postfix start")
        assert 0 != device.expect(['failed']+ device.prompt, timeout = 90), "Unable to start Postfix service.Service is not properly installed"
