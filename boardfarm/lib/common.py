# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import json
import pexpect
import sys
import time
import os
from termcolor import cprint
import re
import ipaddress
from boardfarm.lib.SnmpHelper import SnmpMibs

from selenium import webdriver
from selenium.webdriver.common import proxy
from boardfarm.library import print_bold
from installers import install_pysnmp
from regexlib import ValidIpv4AddressRegex, AllValidIpv6AddressesRegex

ubootprompt = ['ath>', '\(IPQ\) #', 'ar7240>']
linuxprompt = ['root\\@.*:.*#', '@R7500:/# ']
prompts = ubootprompt + linuxprompt + ['/.* # ', ]

def run_once(f):
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return f(*args, **kwargs)
    wrapper.has_run = False
    return wrapper

def spawn_ssh_pexpect(ip, user='root', pw='bigfoot1', prompt=None, port="22", via=None, color=None, o=sys.stdout):
    if via:
        p = via.sendline("ssh %s@%s -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
                                            % (user, ip, port))
        p = via
    else:
        p = pexpect.spawn("ssh %s@%s -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
                                            % (user, ip, port))

    i = p.expect(["yes/no", "assword:", "Last login"], timeout=30)
    if i == 0:
        p.sendline("yes")
        i = p.expect(["Last login", "assword:"])
    if i == 1:
        p.sendline(pw)
    else:
        pass

    if prompt is None:
        p.prompt = "%s@.*$" % user
    else:
        p.prompt = prompt

    p.expect(p.prompt)

    from termcolor import colored
    class o_helper_foo():
        def __init__(self, color):
            self.color = color
        def write(self, string):
            o.write(colored(string, color))
        def flush(self):
            o.flush()

    if color is not None:
        p.logfile_read = o_helper_foo(color)
    else:
        p.logfile_read = o

    return p

def clear_buffer(console):
    try:
        console.read_nonblocking(size=2000, timeout=1)
    except:
        pass

def phantom_webproxy_driver(ipport):
    '''
    Use this if you started web proxy on a machine connected to router's LAN.
    '''
    service_args = [
        '--proxy=' + ipport,
        '--proxy-type=http',
    ]
    print("Attempting to setup Phantom.js via proxy %s" % ipport)
    driver = webdriver.PhantomJS(service_args=service_args)
    driver.set_window_size(1024, 768)
    driver.set_page_load_timeout(30)
    return driver

def firefox_webproxy_driver(ipport, config):
    '''
    Use this if you started web proxy on a machine connected to router's LAN.
    '''

    ip, port = ipport.split(':')

    profile = webdriver.FirefoxProfile()
    profile.set_preference("network.proxy.type", 1)
    profile.set_preference("network.proxy.http", ip)
    profile.set_preference("network.proxy.http_port", int(port))
    profile.set_preference("network.proxy.ssl", ip)
    profile.set_preference("network.proxy.ssl_port", int(port))
    profile.set_preference("network.proxy.ftp", ip)
    profile.set_preference("network.proxy.ftp_port", int(port))
    profile.set_preference("network.proxy.socks", ip)
    profile.set_preference("network.proxy.socks_port", int(port))
    profile.set_preference("network.proxy.socks_remote_dns", True)
    profile.set_preference("browser.download.dir", os.getcwd())
    #number 2 is to save the file to the above current location instead of downloads
    profile.set_preference("browser.download.folderList", 2)
    #added this line to open the file without asking any questions
    profile.set_preference("browser.helperApps.neverAsk.openFile", "text/anytext,text/comma-separated-values,text/csv,application/octet-stream")
    profile.update_preferences()
    driver = webdriver.Firefox(firefox_profile=profile)
    driver.implicitly_wait(30)
    driver.set_page_load_timeout(30)

    return driver

def chrome_webproxy_driver(ipport, config):
    '''
    Use this if you prefer Chrome. Should be the same as firefox_webproxy_driver
    above, although ChromeWebDriver seems to be slower in loading pages.
    '''

    chrome_options = webdriver.ChromeOptions()
    if config.default_proxy_type ==  'socks5':
        chrome_options.add_argument("--proxy-server=socks5://" + ipport);
    else:
        chrome_options.add_argument('--proxy-server=' + ipport)

    chrome_options.add_argument("--start-maximized")

    if "BFT_DEBUG" in os.environ:
        print("chrome can be connected to Xvnc")
    else:
        print("chrome running headless")
        chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)

    driver.implicitly_wait(30)
    driver.set_page_load_timeout(30)

    return driver

def get_webproxy_driver(ipport, config):
    if config.default_web_driver == "ffox":
        d = firefox_webproxy_driver(ipport, config)
        d.maximize_window()
        return d
    elif config.default_web_driver == "chrome":
        return chrome_webproxy_driver(ipport, config)
        # the win maximise is done in the chrome options
    else:
        # something has gone wrong, make the error message as self explanatory as possible
        msg = "No usable web_driver specified, please add one to the board config"
        if config.default_web_driver is not None:
            msg = msg + " (value in config: '"+config.default_web_driver+"' not recognised)"
        else:
            # this should never happen
            msg = msg + "(no default value set, please check boardfarm/config.py)"
        raise Exception(msg)

    print("Using proxy %s, webdriver: %s" % (proxy, config.default_web_driver))

def test_msg(msg):
    cprint(msg, None, attrs=['bold'])

def sha256_checksum(filename, block_size=65536):
    '''Calculates the SHA256 on a file'''
    import hashlib
    sha256 = hashlib.sha256()
    with open(filename, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            sha256.update(block)
    return sha256.hexdigest()

class TestResult:
    logged = {}
    def __init__(self, name, grade, message):
        self.name = name
        self.result_grade = grade
        self.result_message = message

cmd_exists = lambda x: any(os.access(os.path.join(path, x), os.X_OK) for path in os.environ["PATH"].split(os.pathsep))


def start_ipbound_httpservice(device, ip="0.0.0.0", port="9000"):
    '''
    Starts a simple web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop
    '''
    device.sendline("python -c 'import BaseHTTPServer as bhs, SimpleHTTPServer as shs; bhs.HTTPServer((\"%s\", %s), shs.SimpleHTTPRequestHandler).serve_forever()'"%(ip, port))
    if 0 ==device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        if "BFT_DEBUG" in os.environ:
            print_bold("Faield to start service on "+ip+":"+port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on "+ip+":"+port)
        return True

def start_ip6bound_httpservice(device, ip="::", port="9001"):
    '''
    Starts a simple web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop (twice? needs better signal handling)
    '''
    device.sendline('''cat > /root/SimpleHTTPServer6.py<<EOF
import socket
import BaseHTTPServer as bhs
import SimpleHTTPServer as shs

class HTTPServerV6(bhs.HTTPServer):
    address_family = socket.AF_INET6
HTTPServerV6((\"%s\", %s),shs.SimpleHTTPRequestHandler).serve_forever()
EOF'''%(ip, port))

    device.expect(device.prompt)
    device.sendline ("python -m /root/SimpleHTTPServer6")
    if 0 == device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        if "BFT_DEBUG" in os.environ:
            print_bold('Faield to start service on ['+ip+']:'+port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on ["+ip+"]:"+port)
        return True

def start_ipbound_httpsservice(device, ip="0.0.0.0", port="443", cert="/root/server.pem"):
    '''
    Starts a simple HTTPS web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop (twice? needs better signal handling)
    '''
    import re
    # the https server needs a certificate, lets create a bogus one
    device.sendline("openssl req -new -x509 -keyout server.pem -out server.pem -days 365 -nodes")
    for i in range(10):
        if device.expect([re.escape("]:"), re.escape("Email Address []:")]) > 0:
            device.sendline()
            break
        device.sendline()
    device.expect(device.prompt)
    device.sendline("python -c 'import os; print os.path.exists(\"%s\")'"%cert)
    if 1 == device.expect(["True", "False"]):
        # no point in carrying on
        print_bold("Failed to create certificate for HTTPs service")
        return False
    device.expect(device.prompt)
    # create and run the "secure" server
    device.sendline('''cat > /root/SimpleHTTPsServer.py<< EOF
# taken from http://www.piware.de/2011/01/creating-an-https-server-in-python/
# generate server.xml with the following command:
#    openssl req -new -x509 -keyout server.pem -out server.pem -days 365 -nodes
# run as follows:
#    python simple-https-server.py
# then in your browser, visit:
#    https://<ip>:<port>

import BaseHTTPServer, SimpleHTTPServer
import ssl

httpd = BaseHTTPServer.HTTPServer((\"%s\", %s), SimpleHTTPServer.SimpleHTTPRequestHandler)
httpd.socket = ssl.wrap_socket (httpd.socket, certfile=\"%s\", server_side=True)
httpd.serve_forever()
EOF'''%(ip, port, cert))

    device.expect(device.prompt)
    device.sendline ("python -m /root/SimpleHTTPsServer")
    if 0 == device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        print_bold("Failed to start service on ["+ip+"]:"+port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on ["+ip+"]:"+port)
        return True

def start_ip6bound_httpsservice(device, ip="::", port="4443", cert="/root/server.pem"):
    '''
    Starts a simple HTTPS web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop (twice? needs better signal handling)
    '''
    import re
    # the https server needs a certificate, lets create a bogus one
    device.sendline("openssl req -new -x509 -keyout server.pem -out server.pem -days 365 -nodes")
    for i in range(10):
        if device.expect([re.escape("]:"), re.escape("Email Address []:")]) > 0:
            device.sendline()
            break
        device.sendline()
    device.expect(device.prompt)
    device.sendline("python -c 'import os; print os.path.exists(\"%s\")'"%cert)
    if 1 == device.expect(["True", "False"]):
        # no point in carrying on
        print_bold("Failed to create certificate for HTTPs service")
        return False
    device.expect(device.prompt)
    # create and run the "secure" server
    device.sendline('''cat > /root/SimpleHTTPsServer.py<< EOF
import socket
import BaseHTTPServer as bhs
import SimpleHTTPServer as shs
import ssl

class HTTPServerV6(bhs.HTTPServer):
    address_family = socket.AF_INET6
https=HTTPServerV6((\"%s\", %s),shs.SimpleHTTPRequestHandler)
https.socket = ssl.wrap_socket (https.socket, certfile=\"%s\", server_side=True)
https.serve_forever()
EOF'''%(ip, port, cert))

    device.expect(device.prompt)
    device.sendline ("python -m /root/SimpleHTTPsServer")
    if 0 == device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        print_bold("Failed to start service on ["+ip+"]:"+port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on ["+ip+"]:"+port)
        return True

def configure_postfix(device):
    '''
    configures TSL and SSL ports to access postfix server
    The function can be extended with configuration changes to test emails.
    '''
    device.sendline ('''cat > /etc/postfix/master.cf << EOF
smtp      inet  n       -       y       -       -       smtpd
465      inet  n       -       n       -       -       smtpd
587      inet  n       -       n       -       -       smtpd
smtp      inet  n       -       y       -       1       postscreen
smtpd     pass  -       -       y       -       -       smtpd

#628       inet  n       -       y       -       -       qmqpd
pickup    unix  n       -       y       60      1       pickup
cleanup   unix  n       -       y       -       0       cleanup
qmgr      unix  n       -       n       300     1       qmgr
#qmgr     unix  n       -       n       300     1       oqmgr
tlsmgr    unix  -       -       y       1000?   1       tlsmgr
rewrite   unix  -       -       y       -       -       trivial-rewrite
bounce    unix  -       -       y       -       0       bounce
defer     unix  -       -       y       -       0       bounce
trace     unix  -       -       y       -       0       bounce
verify    unix  -       -       y       -       1       verify
flush     unix  n       -       y       1000?   0       flush
proxymap  unix  -       -       n       -       -       proxymap
proxywrite unix -       -       n       -       1       proxymap
smtp      unix  -       -       y       -       -       smtp
relay     unix  -       -       y       -       -       smtp
        -o syslog_name=postfix/$service_name
#       -o smtp_helo_timeout=5 -o smtp_connect_timeout=5
showq     unix  n       -       y       -       -       showq
error     unix  -       -       y       -       -       error
retry     unix  -       -       y       -       -       error
discard   unix  -       -       y       -       -       discard
local     unix  -       n       n       -       -       local
virtual   unix  -       n       n       -       -       virtual
lmtp      unix  -       -       y       -       -       lmtp
anvil     unix  -       -       y       -       1       anvil
scache    unix  -       -       y       -       1       scache
#

maildrop  unix  -       n       n       -       -       pipe
  flags=DRhu user=vmail argv=/usr/bin/maildrop -d ${recipient}

#
uucp      unix  -       n       n       -       -       pipe
  flags=Fqhu user=uucp argv=uux -r -n -z -a$sender - $nexthop!rmail ($recipient)
#
# Other external delivery methods.
#
ifmail    unix  -       n       n       -       -       pipe
  flags=F user=ftn argv=/usr/lib/ifmail/ifmail -r $nexthop ($recipient)
bsmtp     unix  -       n       n       -       -       pipe
  flags=Fq. user=bsmtp argv=/usr/lib/bsmtp/bsmtp -t$nexthop -f$sender $recipient
scalemail-backend unix  -       n       n       -       2       pipe
  flags=R user=scalemail argv=/usr/lib/scalemail/bin/scalemail-store ${nexthop} ${user} ${extension}
mailman   unix  -       n       n       -       -       pipe
  flags=FR user=list argv=/usr/lib/mailman/bin/postfix-to-mailman.py
  ${nexthop} ${user}
EOF''')
    device.expect(device.prompt, timeout = 10)
    device.sendline("service postfix start")
    device.expect(device.prompt)
    device.sendline("service postfix reload")
    assert 0 != device.expect(['failed']+ device.prompt, timeout = 20) , "Unable to reolad server with new configurations"


def file_open_json(file):
    try:
        with open(file) as f:
            return json.load(f)
    except:
        raise Exception("Could not open the json file")

def snmp_mib_set(device, parser, iface_ip, mib_name, index, set_type, set_value, timeout=10, retry=3, community='private'):
    """
    Name: snmp_mib_set
    Purpose: set value of mibs via snmp
    Input: wan, board, prompt, wan_ip, mib_name, index, set_type ,set_value
    Output: set value
    mib_name has to be passed with name of the mib, index is query index
    set_type is "i" or "s" or "a" or "x"
    set_value is the value to be set for the mib
    Usage: snmp_mib_set(wan, board, board.wan_iface, "wifiMgmtBssSecurityMode", "32", "i", "1")
    """
    time_out = (timeout*retry)+30
    extra_arg = ''

    if not isinstance(parser, SnmpMibs):
        match = re.search("\d+.(.*)",parser.mib[mib_name])
        mib_oid = 'iso.'+match.group(1)+'.'+index
        oid = parser.mib[mib_name]
    else:
        extra_arg = ' -On '
        oid = parser.get_mib_oid(mib_name)
        mib_oid = '.' +oid +  '.'+index
    if set_type == "i" or set_type == "a" or set_type == "u" or set_type == "s":
        device.sendline("snmpset -v 2c " +extra_arg+" -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+oid+"."+str(index)+" "+set_type+" "+str(set_value))
        device.expect_exact("snmpset -v 2c " +extra_arg+" -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+oid+"."+str(index)+" "+set_type+" "+str(set_value))
        if set_type != "s":
            idx = device.expect(['Timeout: No Response from'] + [mib_oid+'\s+\=\s+\S+\:\s+(%s)\r\n' % set_value] + device.prompt, timeout=time_out)
        else:
            idx = device.expect(['Timeout: No Response from'] + [mib_oid+'\s+\=\s+\S+\:\s+\"(%s)\"\r\n' % set_value] + device.prompt, timeout=time_out)
    elif set_type == "x":
        device.sendline("snmpset -v 2c -Ox" +extra_arg+" -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+oid+"."+str(index)+" "+set_type+" "+set_value)
        device.expect_exact("snmpset -v 2c -Ox" +extra_arg+" -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+oid+"."+str(index)+" "+set_type+" "+set_value)
        """trimming the prefix 0x , since snmp will return in that format"""
        if "0x" in set_value.lower():
            set_value = set_value[2:]
        set_value_hex = set_value.upper()
        set_value_output = ' '.join([set_value_hex[i:i+2] for i in range(0, len(set_value_hex), 2)])
        idx = device.expect(['Timeout: No Response from'] + [mib_oid+'\s+\=\s+\S+\:\s+(%s)\s+\r\n' % set_value_output] + device.prompt, timeout=40)
    elif set_type == "t" or set_type == "b" or set_type == "o" or set_type == "n" or set_type == "d":
        idx = 0
    elif set_type == "str_with_space":
        set_type = "s"
        set_value = str(set_value)
        device.sendline("snmpset -v 2c " +extra_arg+" -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+oid+"."+str(index)+" "+set_type+" "+"'%s'" %set_value)
        device.expect_exact("snmpset -v 2c " +extra_arg+" -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+oid+"."+str(index)+" "+set_type+" "+"'%s'" %set_value)
        idx = device.expect(['Timeout: No Response from'] + ['STRING: \"(.*)\"\r\n'] + device.prompt, timeout=10)

    assert idx==1,"Setting the mib %s" % mib_name
    snmp_out = device.match.group(1)
    device.expect(device.prompt)
    return snmp_out

def snmp_mib_get(device, parser, iface_ip, mib_name, index, timeout=10, retry=3, community='private', opt_args = ''):
    """
    Name: snmp_mib_get
    Purpose: get the value of mibs via snmp
    Input: wan, board/snmpParser, prompt, wan_ip, mib_name, index
    Output: get value
    mib_name has to be passed with name of the mib, index is query index
    Usage: snmp_mib_set(wan, board/snmpParser, board.wan_iface, "wifiMgmtBssSecurityMode", "32")
    """
    time_out = (timeout*retry)+30
    extra_arg = ''

    # this should allow for legacy behaviour (with board passed in)
    if not isinstance(parser, SnmpMibs):
        match = re.search("\d+.(.*)",parser.mib[mib_name])
        mib_oid = 'iso\.' + match.group(1) + '.'+index
        oid = parser.mib[mib_name]
    else:
        extra_arg = ' -On '
        oid = parser.get_mib_oid(mib_name)
        mib_oid = oid +  '.'+index

    """opt_args attribute added to get the output in hexa value using Ox option"""
    if opt_args != '':
        device.sendline("snmpget -v 2c -Ox"+ extra_arg + " -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+ oid +"."+str(index))
        device.expect_exact("snmpget -v 2c -Ox"+ extra_arg + " -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+ oid +"."+str(index))
    else:
        device.sendline("snmpget -v 2c"+ extra_arg + " -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+ oid +"."+str(index))
        device.expect_exact("snmpget -v 2c"+ extra_arg + " -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+ oid +"."+str(index))
    idx = device.expect(['Timeout: No Response from'] + [mib_oid+'\s+\=\s+\S+\:\s+(.*)\r\n'] + device.prompt, timeout=time_out)
    assert idx==1,"Getting the mib %s"% mib_name
    snmp_out = device.match.group(1)
    device.expect(device.prompt)
    snmp_out = snmp_out.strip("\"").strip()
    return snmp_out

def hex2ipv6(hexstr):
    """
    Can parse strings in this form:
    FE 80 00 00 00 00 00 00 3A 43 7D FF FE DC A6 C3
    """
    hexstr = hexstr.replace(' ', '').lower()
    blocks = (''.join(block) for block in zip(*[iter(hexstr)]*4))
    return ipaddress.IPv6Address(':'.join(str(block) for block in blocks).decode('utf-8'))

def retry(func_name, max_retry, *args):
    for i in range(max_retry):
        output = func_name(*args)
        if output:
            return output
        else:
            time.sleep(5)
    else:
        return None

def retry_on_exception(method, args, retries=10, tout=5):
    """
    Retries a method if an exception occurs
    NOTE: args must be a tuple, hence a 1 arg tuple is (<arg>,)
    """
    output = None
    for not_used in range(retries):
        try:
            output = method(*args)
            break
        except Exception as e:
            print_bold("method failed %d time (%s)"%((not_used+1), e))
            time.sleep(tout)
            pass

    return output

def resolv_dict(dic, key):
    """
    This function used to get the value from gui json, replacement of eval
    """
    key = key.strip("[]'").replace("']['", '#').split('#')
    key_val = dic
    for elem in key:
        key_val = key_val[elem]
    return key_val

def snmp_asyncore_walk(device, ip_address, mib_oid, community='public', time_out=200):
    '''
    Function to do a snmp walk using asyncore script
    '''
    if re.search(ValidIpv4AddressRegex,ip_address):
        mode = 'ipv4'
    elif re.search(AllValidIpv6AddressesRegex, ip_address):
        mode = 'ipv6'
    install_pysnmp(device)
    asyncore_script = 'asyncore_snmp.py'
    fname = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'scripts/'+asyncore_script)
    dest = asyncore_script
    device.copy_file_to_server(fname, dest)
    device.sendline('time python %s %s %s %s %s %s > snmp_output.txt' % (asyncore_script, ip_address, mib_oid, community, time_out, mode))
    device.expect(device.prompt, timeout=time_out)
    device.sendline('rm %s' % asyncore_script)
    device.expect(device.prompt)
    device.sendline('ls -l snmp_output.txt --block-size=kB')
    device.expect(['.*\s+(\d+)kB'])
    file_size = device.match.group(1)
    device.expect(device.prompt)
    if file_size != '0':
        device.sendline('tail snmp_output.txt')
        idx = device.expect("No more variables left in this MIB View")
        if idx == 0:
            device.sendline('rm snmp_output.txt')
            device.expect(device.prompt)
            return True
    else:
        return False

def snmp_mib_walk(device, parser, ip_address, mib_name, community='public', retry=3, time_out=200):
    """
    Name: snmp_mib_walk
    Purpose: walk a mib with small mib tree
    Input: wan, board/snmpParser, prompt, ip_add, mib_name
    Output: Snmpwalk output
    Usage: snmp_mib_walk(wan, board, cm_wan_ip, "wifiMgmtBssSecurityMode")
    """
    if not isinstance(parser, SnmpMibs):
        oid = parser.mib[mib_name]
    else:
        oid = parser.get_mib_oid(mib_name)

    device.sendline("snmpwalk -v 2c -c "+community+" -t " +str(time_out)+ " -r "+str(retry)+" "+ip_address+" "+ oid)
    device.expect(device.prompt)
    snmp_out = device.before
    return snmp_out
