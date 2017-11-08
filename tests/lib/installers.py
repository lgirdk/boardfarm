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
        device.expect('The telnet server', timeout=5)
        device.expect(device.prompt)
    except:
        device.expect(device.prompt)
        device.sendline('apt-get install telnetd -y')
        device.expect(device.prompt)
        device.sendline('echo \"service telnet\" > /etc/xinetd.d/telnet')
        device.sendline('echo "{" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"disable = no\" >> /etc/xinetd.d/telnet')
        device.sendline('echo \"flags = REUSE\" >> /etc/xinetd.d/telnet')
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
        device.expect('The telnet client', timeout=5)
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
