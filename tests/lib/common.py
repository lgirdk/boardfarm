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
import subprocess
import time
import unittest2
import urllib2
import os
import signal
import config
from termcolor import cprint
import re, ipaddress

from selenium import webdriver
from selenium.webdriver.common.proxy import *

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
        i = self.expect(["Last login", "assword:"])
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

def firefox_webproxy_driver(ipport):
    '''
    Use this if you started web proxy on a machine connected to router's LAN.
    '''

    ip, port = ipport.split(':')

    profile = webdriver.FirefoxProfile()
    profile.set_preference("network.proxy.type", 1)
    profile.set_preference("network.proxy.http", ip)
    profile.set_preference("network.proxy.http_port", int(port))
    # missing the ssl proxy, should we add it?
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

def chrome_webproxy_driver(ipport):
    '''
    Use this if you prefer Chrome. Should be the same as firefox_webproxy_driver
    above, although ChromeWebDriver seems to be slower in loading pages.
    '''

    chrome_options = webdriver.ChromeOptions()
    if config.default_proxy_type ==  'sock5':
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

def get_webproxy_driver(ipport):
    if config.default_web_driver == "ffox":
        d = firefox_webproxy_driver(ipport)
        d.maximize_window()
        return d
    elif config.default_web_driver == "chrome":
        return chrome_webproxy_driver(ipport)
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

from library import print_bold
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

def snmp_mib_set(device, board, iface_ip, mib_name, index, set_type, set_value, timeout=10, retry=3):
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
    match = re.search("\d+.(.*)",board.mib[mib_name])
    mib_oid = match.group(1)+'.'+index
    time_out = (timeout*retry)+30
    device.sendline("snmpset -v 2c -c private -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+board.mib[mib_name]+"."+str(index)+" "+set_type+" "+str(set_value))
    if set_type == "i" or set_type == "a" or set_type == "u":
        idx = device.expect(['Timeout: No Response from'] + ['iso\.'+mib_oid+'\s+\=\s+\S+\:\s+(%s)\r\n' % set_value] + device.prompt, timeout=time_out)
    elif set_type == "s":
        idx = device.expect(['Timeout: No Response from'] + ['iso\.'+mib_oid+'\s+\=\s+\S+\:\s+\"(%s)\"\r\n' % set_value] + device.prompt, timeout=time_out)
    elif set_type == "x":
        set_value_hex = set_value[2:].upper()
        set_value_output = ' '.join([set_value_hex[i:i+2] for i in range(0, len(set_value_hex), 2)])
        idx = device.expect(['Timeout: No Response from'] + ['iso\.'+mib_oid+'\s+\=\s+\S+\:\s+(%s)\s+\r\n' % set_value_output] + device.prompt, timeout=40)
    assert idx==1,"Setting the mib %s" % mib_name
    snmp_out = device.match.group(1)
    device.expect(device.prompt)
    return snmp_out

def snmp_mib_get(device, board, iface_ip, mib_name, index, timeout=10, retry=3, community='private'):
    """
    Name: snmp_mib_get
    Purpose: get the value of mibs via snmp
    Input: wan, board, prompt, wan_ip, mib_name, index
    Output: get value
    mib_name has to be passed with name of the mib, index is query index
    Usage: snmp_mib_set(wan, board, board.wan_iface, "wifiMgmtBssSecurityMode", "32")
    """
    match = re.search("\d+.(.*)",board.mib[mib_name])
    mib_oid = match.group(1)+'.'+index
    time_out = (timeout*retry)+30
    device.sendline("snmpget -v 2c -c "+community+" -t " +str(timeout)+ " -r "+str(retry)+" "+iface_ip+" "+board.mib[mib_name]+"."+str(index))
    idx = device.expect(['Timeout: No Response from'] + ['iso\.'+mib_oid+'\s+\=\s+\S+\:\s+(.*)\r\n'] + device.prompt, timeout=time_out)
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

def setup_asterisk_config(device,numbers):
    # to add sip.conf and extensions.conf
    gen_conf = '''cat > /etc/asterisk/sip.conf << EOF
[general]
context=default
bindport=5060
allowguest=yes
qualify=yes
registertimeout=900
allow=all
allow=alaw
allow=gsm
allow=g723
allow=g729
EOF'''
    gen_mod = '''cat > /etc/asterisk/extensions.conf << EOF
[default]
EOF'''
    device.sendline(gen_conf)
    device.expect(device.prompt)
    device.sendline(gen_mod)
    device.expect(device.prompt)
    for i in numbers:
        num_conf = '''(
echo ['''+i+''']
echo type=friend
echo regexten='''+i+'''
echo secret=1234
echo qualify=no
echo nat=force_rport
echo host=dynamic
echo canreinvite=no
echo context=default
echo dial=SIP/'''+i+'''
)>>  /etc/asterisk/sip.conf'''
        device.sendline(num_conf)
        device.expect(device.prompt)
        num_mod = '''(
echo exten \=\> '''+i+''',1,Dial\(SIP\/'''+i+''',10,r\)
echo same \=\>n,Wait\(20\)
)>> /etc/asterisk/extensions.conf'''
        device.sendline(num_mod)
        device.expect(device.prompt)
