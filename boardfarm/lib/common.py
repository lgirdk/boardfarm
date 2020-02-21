# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import base64
import binascii
import ipaddress
import json
import netrc
import os
import re
import ssl
import sys
import time

import termcolor
import pexpect

from termcolor import cprint
from boardfarm.lib.SnmpHelper import SnmpMibs
from boardfarm.lib.installers import install_postfix
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from datetime import datetime
try:
    # Python3
    from urllib.parse import urlparse
    from urllib.request import urlopen, Request
except:
    # Python2
    from urlparse import urlparse
    from urllib2 import urlopen, Request

from selenium import webdriver
from selenium.webdriver.common import proxy
from .installers import install_pysnmp

ubootprompt = ['ath>', r'\(IPQ\) #', 'ar7240>']
linuxprompt = ['root\\@.*:.*#', '@R7500:/# ']
prompts = ubootprompt + linuxprompt + ['/.* # ', ]

def run_once(f):
    """Decorator to run a function only once.

    :param f: function name to run only once
    :type f: Object
    :return: Output of the function for the first run, Other calls to it will return None
    :rtype: Any(for first run), None for Other calls
    """
    def wrapper(*args, **kwargs):
        """Wrapper function that caches the result for all future arguments and will not run the function again.

        :param args: any number of extra arguments
        :type args: Arguments(args)
        :param kwargs: arguments, where you provide a name to the variable as you pass it into the function
        :type kwargs: Arguments(args)
        :return: Output of the function
        :rtype: Any
        """
        if not wrapper.has_run:
            wrapper.has_run = True
            return f(*args, **kwargs)
    wrapper.has_run = False
    return wrapper

def clear_buffer(console):
    """Clears buffer size of 2000 characters from the console of the device

    :param console: console of a device (lan, wan, board etc.,)
    :type console: Object
    """
    try:
        console.read_nonblocking(size=2000, timeout=1)
    except:
        pass

def phantom_webproxy_driver(ipport):
    """Use this if you started phantom web proxy on a machine connected to router's LAN.
    A proxy server sits between a client application, such as a Web browser, and a real server.
    It intercepts all requests to the real server to see if it can fulfill the requests itself.
    If not, it forwards the request to the real server

    :param ipport: ip address and port number
    :type ipport: String
    :return: gui selenium web driver
    :rtype: selenium webdriver element
    """
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
    """Use this if you started firefox web proxy on a machine connected to router's LAN.
    A proxy server sits between a client application, such as a Web browser, and a real server.
    It intercepts all requests to the real server to see if it can fulfill the requests itself.
    If not, it forwards the request to the real server

    :param ipport: ip and port number
    :type ipport: String
    :param config: web elements in Json file
    :type config: Json
    :return: gui selenium web driver
    :rtype: selenium webdriver element
    """

    ip, port = ipport.split(':')

    profile = webdriver.FirefoxProfile()
    if config.default_proxy_type == 'socks5':
        # socks5 section MUST be separated or it will NOT work!!!!
        profile.set_preference("network.proxy.socks", ip)
        profile.set_preference("network.proxy.socks_port", int(port))
        profile.set_preference("security.enterprise_roots.enabled", True)
        profile.set_preference("network.proxy.socks_version", 5)
    else:
        profile.set_preference("network.proxy.type", 1)
        profile.set_preference("network.proxy.http", ip)
        profile.set_preference("network.proxy.http_port", int(port))
        profile.set_preference("network.proxy.ssl", ip)
        profile.set_preference("network.proxy.ssl_port", int(port))
        profile.set_preference("network.proxy.ftp", ip)
        profile.set_preference("network.proxy.ftp_port", int(port))
    # number 2 is to save the file to the above current location instead of downloads
    profile.set_preference("browser.download.folderList", 2)
    # added this line to open the file without asking any questions
    profile.set_preference("browser.helperApps.neverAsk.openFile", "text/anytext,text/comma-separated-values,text/csv,application/octet-stream")
    profile.update_preferences()
    driver = webdriver.Firefox(firefox_profile=profile)
    x,y = config.get_display_backend_size()
    driver.set_window_size(x, y)
    driver.implicitly_wait(30)
    driver.set_page_load_timeout(30)

    return driver

def chrome_webproxy_driver(ipport, config):
    """Use this if you prefer Chrome. Should be the same as firefox_webproxy_driver
    above, although ChromeWebDriver seems to be slower in loading pages.
    A proxy server sits between a client application, such as a Web browser, and a real server.
    It intercepts all requests to the real server to see if it can fulfill the requests itself.
    If not, it forwards the request to the real server

    :param ipport: ip and port number
    :type ipport: String
    :param config: web elements in Json file
    :type config: Json
    :return: gui selenium web driver
    :rtype: selenium webdriver element
    """

    chrome_options = webdriver.ChromeOptions()
    if config.default_proxy_type == 'socks5':
        chrome_options.add_argument("--proxy-server=socks5://" + ipport)
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
    """Get the web driver initialized based on the web driver configurations in config.py

    :param ipport: ip and port number
    :type ipport: String
    :param config: web elements in Json file
    :type config: Json
    :raise Exception: Exception thrown when default web driver is None or not recognized
    :return: gui selenium web driver for ffox and chrome
    :rtype: selenium webdriver element
    """
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
            msg = msg + " (value in config: '" + config.default_web_driver + "' not recognised)"
        else:
            # this should never happen
            msg = msg + "(no default value set, please check boardfarm/config.py)"
        raise Exception(msg)

    print("Using proxy %s, webdriver: %s" % (proxy, config.default_web_driver))

def test_msg(msg):
    """Prints the message in Bold

    :param msg: Message to print in bold
    :type msg: String
    """
    cprint(msg, None, attrs=['bold'])

def _hash_file(filename, block_size, hashobj):
    """Helper function: Initialize a hash obj and digests a file through it.
    Calculates an md5sum based on the contents of the filename by calling digest()

    :param filename: Name of the file to calculate hash value
    :type filename: String
    :param block_size: How many bytes of the file you want to open at a time
    :type block_size: Integer
    :param hashobj: Type of algorithm to calculate hash
    :type hashobj: Hash
    :return: Returns the hash value in hexadecimal format
    :rtype: hex
    """
    with open(filename, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            hashobj.update(block)
    return hashobj.hexdigest()

def sha256_checksum(filename, block_size=65536):
    """Calculates the SHA256 on a file.
    SHA-256 generates an almost-unique 256-bit signature for a text

    :param filename: Name of the file to calculate hash value
    :type filename: String
    :param block_size: bytes of the file you want to open at a time, defaults to 65536
    :type block_size: Integer, optional
    :return: Returns the hash value in hexadecimal format
    :rtype: hex
    """
    import hashlib
    sha256 = hashlib.sha256()
    return _hash_file(filename, block_size, sha256)

def keccak512_checksum(filename, block_size=65536):
    """Calculates the SHA3 hash on a file.
    SHA-512 or keccak512 generates an almost-unique 512-bit signature for a text

    :param filename: Name of the file to calculate hash value
    :type filename: String
    :param block_size: bytes of the file you want to open at a time, defaults to 65536
    :type block_size: Integer, optional
    :return: Returns the hash value in hexadecimal format
    :rtype: hex
    """
    from Crypto.Hash import keccak
    keccak_hash = keccak.new(digest_bits=512)
    return _hash_file(filename, block_size, keccak_hash)

cmd_exists = lambda x: any(os.access(os.path.join(path, x), os.X_OK) for path in os.environ["PATH"].split(os.pathsep))


def start_ipbound_httpservice(device, ip="0.0.0.0", port="9000", options=""):
    """Starts a simple IPv4 web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop

    :param device: lan or wan
    :type device: Object
    :param ip: Ip address on which http service to run, defaults to "0.0.0.0"
    :type ip: String, Optional
    :param port: port number on which http service to run, defaults to "9000"
    :type port: String, Optional
    :param options: Additional options which can be used to run in background, or store the console log to a file.
                    Example: To run the service in background, you can pass "2>&1 &"
    :type options: String, Optional, defaults to empty
    :return: True or False
    :rtype: Boolean
    """
    http_service_kill(device, "SimpleHTTPServer")
    device.sendline("python -c 'import BaseHTTPServer as bhs, SimpleHTTPServer as shs; bhs.HTTPServer((\"%s\", %s), shs.SimpleHTTPRequestHandler).serve_forever()' %s" % (ip, port, options))
    if 0 == device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        if "BFT_DEBUG" in os.environ:
            print_bold("Faield to start service on " + ip + ":" + port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on " + ip + ":" + port)
        return True

def start_ip6bound_httpservice(device, ip="::", port="9001", options=""):
    """Starts a simple IPv6 web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop (twice? needs better signal handling)

    :param device: lan or wan
    :type device: Object
    :param ip: Ipv6 address on which ipv6 http service to run, defaults to "::"
    :type ip: String, Optional
    :param port: port number on which ipv6 http service to run, defaults to "9001"
    :type port: String, Optional
    :param options: Additional options which can be used to run in background, or store the console log to a file.
                    Example: To run the service in background, you can pass "2>&1 &"
    :type options: String, Optional, defaults to empty
    :return: True or False
    :rtype: Boolean
    """
    http_service_kill(device, "SimpleHTTPServer")
    device.sendline('''cat > /root/SimpleHTTPServer6.py<<EOF
import socket
import BaseHTTPServer as bhs
import SimpleHTTPServer as shs

class HTTPServerV6(bhs.HTTPServer):
    address_family = socket.AF_INET6
HTTPServerV6((\"%s\", %s),shs.SimpleHTTPRequestHandler).serve_forever()
EOF''' % (ip, port))

    device.expect(device.prompt)
    device.sendline("python -m /root/SimpleHTTPServer6 %s" %options)
    if 0 == device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        if "BFT_DEBUG" in os.environ:
            print_bold('Faield to start service on [' + ip + ']:' + port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on [" + ip + "]:" + port)
        return True

def start_ipbound_httpsservice(device, ip="0.0.0.0", port="443", cert="/root/server.pem", options=""):
    """Starts a simple IPv4 HTTPS web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop (twice? needs better signal handling)

    :param device: lan or wan
    :type device: Object
    :param ip: Ip address on which https service to run, defaults to "0.0.0.0"
    :type ip: String, Optional
    :param port: port number on which https service to run, defaults to "443"
    :type port: String, Optional
    :param cert: SSL certificate location, defaults to "/root/server.pem"
    :type cert: String, Optional
    :param options: Additional options which can be used to run in background, or store the console log to a file.
                    Example: To run the service in background, you can pass "2>&1 &"
    :type options: String, Optional, defaults to empty
    :return: True or False
    :rtype: Boolean
    """
    import re
    http_service_kill(device, "SimpleHTTPsServer")
    # the https server needs a certificate, lets create a bogus one
    device.sendline("openssl req -new -x509 -keyout server.pem -out server.pem -days 365 -nodes")
    for i in range(10):
        if device.expect([re.escape("]:"), re.escape("Email Address []:")]) > 0:
            device.sendline()
            break
        device.sendline()
    device.expect(device.prompt)
    device.sendline("python -c 'import os; print os.path.exists(\"%s\")'" % cert)
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
EOF''' % (ip, port, cert))

    device.expect(device.prompt)
    device.sendline("python -m /root/SimpleHTTPsServer %s" %options)
    if 0 == device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        print_bold("Failed to start service on [" + ip + "]:" + port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on [" + ip + "]:" + port)
        return True

def start_ip6bound_httpsservice(device, ip="::", port="4443", cert="/root/server.pem", options=""):
    """Starts a simple IPv6 HTTPS web service on a specified port,
    bound to a specified interface. (e.g. tun0)
    Send ctrl-c to stop (twice? needs better signal handling)

    :param device: lan or wan
    :type device: Object
    :param ip: Ipv6 address on which https service to run, defaults to "::"
    :type ip: String, Optional
    :param port: port number on which https service to run, defaults to "4443"
    :type port: String, Optional
    :param cert: SSL certificate location, defaults to "/root/server.pem"
    :type cert: String, Optional
    :param options: Additional options which can be used to run in background, or store the console log to a file.
                    Example: To run the service in background, you can pass "2>&1 &"
    :type options: String, Optional, defaults to empty
    :return: True or False
    :rtype: Boolean
    """
    import re
    http_service_kill(device, "SimpleHTTPsServer")
    # the https server needs a certificate, lets create a bogus one
    device.sendline("openssl req -new -x509 -keyout server.pem -out server.pem -days 365 -nodes")
    for i in range(10):
        if device.expect([re.escape("]:"), re.escape("Email Address []:")]) > 0:
            device.sendline()
            break
        device.sendline()
    device.expect(device.prompt)
    device.sendline("python -c 'import os; print os.path.exists(\"%s\")'" % cert)
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
EOF''' % (ip, port, cert))

    device.expect(device.prompt)
    device.sendline("python -m /root/SimpleHTTPsServer %s" %options)
    if 0 == device.expect(['Traceback', pexpect.TIMEOUT], timeout=10):
        print_bold("Failed to start service on [" + ip + "]:" + port)
        return False
    else:
        if "BFT_DEBUG" in os.environ:
            print_bold("Service started on [" + ip + "]:" + port)
        return True

def configure_postfix(device):
    """configures TSL and SSL ports to access postfix server
    The function can be extended with configuration changes to test emails.

    :param device: lan or wan
    :type device: Object
    :raise assertion: Asserts if service reload fails
    """
    device.sendline('''cat > /etc/postfix/master.cf << EOF
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
    device.expect(device.prompt, timeout=10)
    device.sendline("service postfix start")
    device.expect(device.prompt)
    device.sendline("service postfix reload")
    assert 0 != device.expect(['failed'] + device.prompt, timeout=20), "Unable to reolad server with new configurations"


def file_open_json(file):
    """Reads json file from the location input

    :param file: path of the json file
    :type file: String
    :return: contents of json
    :rtype: dictionary(dict)
    :raise Exception: Throws exception if unable to load file
    """
    try:
        with open(file) as f:
            return json.load(f)
    except Exception as e:
        print(e)
        raise Exception("Could not open the json file")

def snmp_mib_set(device, parser, iface_ip, mib_name, index, set_type, set_value, timeout=10, retry=3, community='private'):
    """set value of mibs via snmp.
    Usage: snmp_mib_set(wan, board, board.wan_ip, "wifiMgmtBssSecurityMode", "32", "i", "1")

    :param device: device where SNMP command shall be executed
    :type device: Object
    :param parser: to parse the mib file
    :type parser: Parser
    :param iface_ip: Management ip of the DUT
    :type iface_ip: String
    :param mib_name: Snmp mib for which value to be set
    :type mib_name: String
    :param index: mib oid index
    :type index: String
    :param set_type: type of value to set
    :type set_type: Data type(i-integer, s-string, x-Hex string etc.,)
    :param set_value: Value to set
    :type set_value: String or integer
    :param timeout: time out for every snmp set request, default to 10 seconds
    :type timeout: Integer, Optional
    :param retry: Number of retries on snmp set request failure, default to 3
    :type retry: Integer, Optional
    :param community: SNMP Community string that allows access to DUT, defaults to 'private'
    :type community: String, optional
    :return: returns the value set
    :rtype: String
    :raise Assertion: Asserts when Snmp set requests timeout
    """
    time_out = (timeout * retry) + 30
    extra_arg = ''

    if not isinstance(parser, SnmpMibs):
        match = re.search(r"\d+.(.*)", parser.mib[mib_name])
        mib_oid = 'iso.' + match.group(1) + '.' + index
        oid = parser.mib[mib_name]
    else:
        extra_arg = ' -On '
        oid = parser.get_mib_oid(mib_name)
        mib_oid = '.' + oid + '.' + index
    if set_type == "i" or set_type == "a" or set_type == "u" or set_type == "s":
        device.sendline("snmpset -v 2c " + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index) + " " + set_type + " " + str(set_value))
        device.expect_exact("snmpset -v 2c " + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index) + " " + set_type + " " + str(set_value))
        if set_type != "s":
            idx = device.expect(['Timeout: No Response from'] + [mib_oid + r'\s+\=\s+\S+\:\s+(%s)\r\n' % set_value] + device.prompt, timeout=time_out)
        else:
            idx = device.expect(['Timeout: No Response from'] + [mib_oid + '\s+\=\s+\S+\:\s+\"(%s)\"\r\n' % set_value] + device.prompt, timeout=time_out)
    elif set_type == "x":
        device.sendline("snmpset -v 2c -Ox" + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index) + " " + set_type + " " + set_value)
        device.expect_exact("snmpset -v 2c -Ox" + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index) + " " + set_type + " " + set_value)
        """trimming the prefix 0x , since snmp will return in that format"""
        if "0x" in set_value.lower():
            set_value = set_value[2:]
        set_value_hex = set_value.upper()
        set_value_output = ' '.join([set_value_hex[i:i + 2] for i in range(0, len(set_value_hex), 2)])
        idx = device.expect(['Timeout: No Response from'] + [mib_oid + r'\s+\=\s+\S+\:\s+(%s)\s+\r\n' % set_value_output] + device.prompt, timeout=40)
    elif set_type == "t" or set_type == "b" or set_type == "o" or set_type == "n" or set_type == "d":
        idx = 0
    elif set_type == "str_with_space":
        set_type = "s"
        set_value = str(set_value)
        device.sendline("snmpset -v 2c " + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index) + " " + set_type + " " + "'%s'" % set_value)
        device.expect_exact("snmpset -v 2c " + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index) + " " + set_type + " " + "'%s'" % set_value)
        idx = device.expect(['Timeout: No Response from'] + ['STRING: \"(.*)\"\r\n'] + device.prompt, timeout=10)

    assert idx == 1, "Setting the mib %s" % mib_name
    snmp_out = device.match.group(1)
    device.expect(device.prompt)
    return snmp_out

def snmp_mib_get(device, parser, iface_ip, mib_name, index, timeout=10, retry=3, community='private', opt_args=''):
    """Get value of mibs via snmp.
    Usage: snmp_mib_set(wan, board/snmpParser, board.wan_iface, "wifiMgmtBssSecurityMode", "32")

    :param device: device where SNMP command shall be executed
    :type device: Object
    :param parser: to parse the mib file
    :type parser: Parser
    :param iface_ip: Management ip of the DUT
    :type iface_ip: String
    :param mib_name: Snmp mib for which value to be set
    :type mib_name: String
    :param index: mib oid index
    :type index: String
    :param timeout: time out for every snmp set request, default to 10 seconds
    :type timeout: Integer, Optional
    :param retry: Number of retries on snmp set request failure, default to 3
    :type retry: Integer, Optional
    :param community: SNMP Community string that allows access to DUT, defaults to 'private'
    :type community: String, optional
    :param opt_args: opt_args attribute added to get the output in hexa value using Ox option, default to ''
    :type opt_args: String, Optional
    :return: Output value of get request
    :rtype: String
    :raise Assertion: Asserts when Snmp get requests timeout
    """
    time_out = (timeout * retry) + 30
    extra_arg = ''

    # this should allow for legacy behaviour (with board passed in)
    if not isinstance(parser, SnmpMibs):
        match = re.search(r"\d+.(.*)", parser.mib[mib_name])
        mib_oid = r'iso\.' + match.group(1) + '.' + index
        oid = parser.mib[mib_name]
    else:
        extra_arg = ' -On '
        oid = parser.get_mib_oid(mib_name)
        mib_oid = oid + '.' + index

    """opt_args attribute added to get the output in hexa value using Ox option"""
    if opt_args != '':
        device.sendline("snmpget -v 2c -Ox" + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index))
        device.expect_exact("snmpget -v 2c -Ox" + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index))
    else:
        device.sendline("snmpget -v 2c" + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index))
        device.expect_exact("snmpget -v 2c" + extra_arg + " -c " + community + " -t " + str(timeout) + " -r " + str(retry) + " " + iface_ip + " " + oid + "." + str(index))
    idx = device.expect(['Timeout: No Response from'] + [mib_oid + r'\s+\=\s+\S+\:\s+(.*)\r\n'] + device.prompt, timeout=time_out)
    assert idx == 1, "Getting the mib %s" % mib_name
    snmp_out = device.match.group(1)
    device.expect(device.prompt)
    snmp_out = snmp_out.strip("\"").strip()
    return snmp_out

def hex2ipv6(hexstr):
    """converts hex string to IPv6 Address

    :param hexstr: ipv6 address in string(FE 80 00 00 00 00 00 00 3A 43 7D FF FE DC A6 C3)
    :type hexstr: String
    :return: IPv6 address
    :rtype: Unicode
    """
    hexstr = hexstr.replace(' ', '').lower()
    blocks = (''.join(block) for block in zip(*[iter(hexstr)] * 4))
    return ipaddress.IPv6Address(':'.join(str(block) for block in blocks).decode('utf-8'))

def retry(func_name, max_retry, *args):
    """Retry a function if the output of the function is false

    :param func_name: name of the function to retry
    :type func_name: Object
    :param max_retry: Maximum number of times to be retried
    :type max_retry: Integer
    :param args: Arguments passed to the function
    :type args: args
    :return: Output of the function if function is True
    :rtype: Boolean (True) or None Type(None)
    """
    for i in range(max_retry):
        output = func_name(*args)
        if output and output != 'False':
            return output
        else:
            time.sleep(5)
    else:
        return None


def retry_on_exception(method, args, retries=10, tout=5):
    """Retry a method if any exception occurs.

    Eventually, at last, throw the exception.
    NOTE: args must be a tuple, hence a 1 arg tuple is (<arg>,)

    :param method: name of the function to retry
    :type method: Object
    :param args: Arguments passed to the function
    :type args: args
    :param retries: Maximum number of retries when a exception occur,
    defaults to 10. When negative, no retries are made.
    :type retries: Integer, Optional
    :param tout: Sleep time after every exception occur, defaults to 5
    :type tout: Integer, Optional
    :return: Output of the function
    :rtype: Any data type
    """
    for not_used in range(retries):
        try:
            return method(*args)
        except Exception as e:    # pylint: disable=broad-except
            print_bold("method failed %d time (%s)" % ((not_used + 1), e))
            time.sleep(tout)
    return method(*args)


def resolv_dict(dic, key):
    """This function used to get the value from gui json, replacement of eval

    :param dic: Dictionary to resolve
    :type dic: Dictionary(dict)
    :param key: Search Key for value needs to be found
    :type key: String or a tree
    :return: Value of the key
    :rtype: String
    """
    key = key.strip("[]'").replace("']['", '#').split('#')
    key_val = dic
    for elem in key:
        key_val = key_val[elem]
    return key_val

def snmp_mib_walk(device, parser, ip_address, mib_name, community='public', retry=3, time_out=100):
    """walk a mib with small mib tree
    Usage: snmp_mib_walk(wan, board, cm_wan_ip, "wifiMgmtBssSecurityMode")

    :param device: device where SNMP command shall be executed
    :type device: Object
    :param parser: to parse the mib file
    :type parser: Parser
    :param ip_address: Management ip of the DUT
    :type ip_address: String
    :param mib_name: Snmp mib for which value to be set
    :type mib_name: String
    :param community: SNMP Community string that allows access to DUT, defaults to 'public'
    :type community: String, optional
    :param retry: Number of retries on snmp set request failure, default to 3
    :type retry: Integer, Optional
    :param time_out: time out for every snmp walk request, default to 100 seconds
    :type time_out: Integer, Optional
    :return: Output value of SNMP walk request
    :rtype: String
    """
    if not isinstance(parser, SnmpMibs):
        oid = parser.mib[mib_name]
    else:
        oid = parser.get_mib_oid(mib_name)

    device.sendline("snmpwalk -v 2c -c " + community + " -t " + str(time_out) + " -r " + str(retry) + " " + ip_address + " " + oid)
    i = device.expect([pexpect.TIMEOUT] + device.prompt, timeout=(time_out * retry) + 10)  # +10 just to be sure
    if i != 0:
        # we have a prompt, so we assume the walk completed ok
        snmp_out = device.before
    else:
        # the expect timed out, try to recover and return None
        snmp_out = None
        device.sendcontrol('c')  # in case the walk is frozen/stuck
        device.expect(device.prompt)
    return snmp_out

def snmp_set_counter32(device, wan_ip, parser, mib_set, value='1024'):
    """Set snmp which has type as counter32(couldn't set it via SNMP)
    Usage: snmp_set_counter32(wan, self.cm_wan_ip, self.snmp_obj, mib_file['Ftp_Us_FileSize'], value='1000')

    :param device: device where SNMP command shall be executed
    :type device: Object
    :param wan_ip: Management ip of the DUT
    :type wan_ip: String
    :param parser: to parse the mib file
    :type parser: Parser
    :param mib_set: Snmp mib for which the value to set
    :type mib_set: String
    :param value: counter32 value to be set for the mib
    :type value: String, optional
    :return: True
    :rtype: Boolean
    :raises Exception: Throws exception when failed to set the mib value
    """
    install_pysnmp(device)
    pysnmp_file = 'pysnmp_mib_set.py'
    device.sendline("python")
    device.expect(">>>")
    device.sendline("f = open('" + pysnmp_file + "'" + ", 'w')")
    device.expect(">>>")
    device.sendline("f.write('from pysnmp.entity.rfc3413.oneliner import cmdgen')")
    device.expect(">>>")
    device.sendline("exit()")
    device.expect(device.prompt)
    command = [("sed -i '1a from pysnmp.proto import rfc1902' " + pysnmp_file),
               ("sed -i '2a wan_ip = " + '"' + wan_ip + '"' + "' " + pysnmp_file),\
               ("sed -i '3a oid = " + '"' + parser.get_mib_oid(mib_set) + '.0"' + "' " + pysnmp_file),\
               ("sed -i '4a value = " + '"' + value + '"' + "' " + pysnmp_file),\
               ("sed -i '5a community = " + '"public"' + "' " + pysnmp_file),\
               ("sed -i '6a value = rfc1902.Counter32(value)' " + pysnmp_file),\
               ("sed -i '7a cmdGen = cmdgen.CommandGenerator()' " + pysnmp_file),\
               ("sed -i '8a cmdGen.setCmd(' " + pysnmp_file),\
               ("sed -i '9a cmdgen.CommunityData(community),' " + pysnmp_file),\
               ("sed -i '10a cmdgen.UdpTransportTarget((wan_ip, 161), timeout=1, retries=3),' " + pysnmp_file),\
               ("sed -i '11a (oid, value))' " + pysnmp_file),\
               ("python " + pysnmp_file),\
               ("rm " + pysnmp_file),\
               ]
    try:
        for i in command:
            device.sendline(i)
            device.expect(device.prompt)
        return True
    except:
        raise Exception("Failed in setting mib using pysnmp")

def snmp_mib_bulkwalk(device, ip_address, mib_oid, time_out=90, retry=3, community='public', expect_content=None):
    """uses SNMP GETBULK requests to query a network entity efficiently for a tree of information
    Usage: snmp_mib_bulkwalk(device, ip_address, mib_oid)

    :param device: device where SNMP command shall be executed
    :type device: Object
    :param ip_address: Management ip of the DUT
    :type ip_address: String
    :param mib_oid: Snmp mib for which value to be set
    :type mib_oid: String
    :param time_out: time out for every snmp walk request, default to 90 seconds
    :type time_out: Integer, Optional
    :param retry: Number of retries on snmp set request failure, default to 3
    :type retry: Integer, Optional
    :param community: SNMP Community string that allows access to DUT, defaults to 'public'
    :type community: String, optional
    :param except_sting: except string for query or wait to prompt
    :type except_sting: String
    :return: true or False
    :type: bool
    """

    device.sendline("snmpbulkwalk -v2c -c %s -Cr25 -Os -t %s -r %s %s %s" % (community, time_out, retry, ip_address, mib_oid))
    if expect_content != None:
        idx = device.expect([expect_content, "Timeout: No Response"], timeout=(time_out * retry) + 30)
    else:
        idx = device.expect(["It is past the end of the MIB tree", "Timeout: No Response"], timeout=(time_out * retry) + 30)
    device.expect(device.prompt)
    return idx == 0

def get_file_magic(fname, num_bytes=4):
    """Return the first few bytes from a file to determine the file type.

    :param fname: file name with location or URL
    :type fname: String
    :param num_bytes: Number of bytes to read from file, defaults to 4
    :type num_bytes: Integer, Optional
    :return: binascii - Interpret the data as binary and shown in hex,
             hexlify represent the binascii result as string
    :rtype: String
    """
    if fname.startswith("http://") or fname.startswith("https://"):
        rng = 'bytes=0-%s' % (num_bytes - 1)
        req = Request(fname, headers={'Range': rng})
        data = urlopen(req).read()
    else:
        f = open(fname, 'rb')
        data = f.read(num_bytes)
        f.close()
    return binascii.hexlify(data)


def copy_file_to_server(cmd, password, target="/tftpboot/"):
    """Requires a command like ssh/scp to transfer a file, and a password.
    Run the command and enter the password if asked for one.
    NOTE: The command must print the filename once the copy has completed

    :param cmd: ssh/scp command to copy file to server
    :type cmd: String
    :param password: password of the server(target)
    :type password: String
    :param target: target location on the server to which the file needs to be copied, defaults to "/tftpboot/"
    :type target: String, Optional
    :return: returns file name after copying
    :rtype: String
    :raises Exception: Exception thrown on copy file failed
    """
    for attempt in range(5):
        try:
            print_bold(cmd)
            p = bft_pexpect_helper.spawn(command='/bin/bash', args=['-c', cmd], timeout=240)
            p.logfile_read = sys.stdout

            i = p.expect(["yes/no", "password:", "%s.*" % target])
            if i == 0:
                p.sendline("yes")
                i = p.expect(["not used", "password:", "%s.*" % target], timeout=45)

            if i == 1:
                p.sendline("%s" % password)
                p.expect("%s.*" % target, timeout=120)

            fname = p.match.group(0).strip()
            print_bold("\nfile: %s" % fname)
        except pexpect.EOF:
            print_bold("EOF exception: unable to extract filename (should be echoed by command)!")
            print_bold("EOF exception: command: %s" % cmd)
        except Exception as e:
            print_bold(e)
            print_bold("tried to copy file to server and failed!")
        else:
            return fname[10:]

        print_bold("Unable to copy file to server, exiting")
        raise Exception("Unable to copy file to server")


def download_from_web(url, server, username, password, port):
    """Download a file from web by framing curl command and using "copy_file_to_server" function

    :param url: URL to download the file
    :type url: String
    :param server: Web Server name or ip
    :type server: String
    :param username: Username to login to the server
    :type username: String
    :param password: password for authentication
    :type password: String
    :param port: port number on which the server is hosted
    :type port: String
    :return: returns file name after copying
    :rtype: String
    :raises Exception: Exception thrown on copy file failed
    """
    pipe = ""
    if cmd_exists('pv'):
        pipe = " pv | "

    cmd = "curl -n -L -k '%s' 2>/dev/null | %s ssh -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -x %s@%s \"mkdir -p /tftpboot/tmp; tmpfile=\`mktemp /tftpboot/tmp/XXXXX\`; cat - > \$tmpfile; chmod a+rw \$tmpfile; echo \$tmpfile\"" % (
        url, pipe, port, username, server)
    return copy_file_to_server(cmd, password)


def scp_to_tftp_server(fname, server, username, password, port):
    """Secure copy file to tftp server using copy_file_to_server

    :param fname: filename to be copied to TFTP server
    :type fname: String
    :param server: tftp Server name or ip
    :type server: String
    :param username: Username to login to the server
    :type username: String
    :param password: password for authentication
    :type password: String
    :param port: port number on which the server is hosted
    :type port: String
    :return: returns file name after copying
    :rtype: String
    :raises Exception: Exception thrown on copy file failed
    """
    # local file verify it exists first
    if not os.path.isfile(fname):
        print_bold("File passed as parameter does not exist! Failing!\n")
        sys.exit(10)

    pipe = ""
    if cmd_exists('pv'):
        pipe = " pv | "

    cmd = "cat %s | %s ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p %s -x %s@%s \"mkdir -p /tftpboot/tmp; tmpfile=\`mktemp /tftpboot/tmp/XXXXX\`; cat - > \$tmpfile; chmod a+rw \$tmpfile; echo \$tmpfile\"" % (
        fname, pipe, port, username, server)
    return copy_file_to_server(cmd, password)


def scp_from(fname, server, username, password, port, dest):
    """Secure copy file from server using copy_file_to_server

    :param fname: filename to be copied to TFTP server
    :type fname: String
    :param server: Server name or ipaddress
    :type server: String
    :param username: Username to login to the server
    :type username: String
    :param password: password for authentication
    :type password: String
    :param port: port number on which the server is hosted
    :type port: String
    :param dest: Destination location with filename to save in local
    :type dest: String
    :return: returns file name after copying
    :rtype: String
    :raises Exception: Exception thrown on copy file failed
    """
    cmd = "scp -P %s -r %s@%s:%s %s; echo DONE" % (port, username, server, fname, dest)
    copy_file_to_server(cmd, password, target='DONE')


def print_bold(msg):
    """Prints the input message in Bold

    :param msg: Message to print in bold
    :type msg: String
    """
    termcolor.cprint(msg, None, attrs=['bold'])

def check_url(url):
    """validates the input URL. Parses the input URL and checks for error

    :param url: Web address to be validated
    :type url: String
    :return: True or False
    :rtype: Boolean
    """
    try:
        def add_basic_auth(login_str, request):
            """Adds Basic auth to http request, pass in login:password as string.
            Usage is within the function.

            :param login_str: parsed login and password in "login:password" format
            :type login_str: String
            :param request: request to upen url
            :type request: String
            """
            encodeuser = base64.b64encode(login_str.encode('utf-8')).decode("utf-8")
            authheader = "Basic %s" % encodeuser
            request.add_header("Authorization", authheader)

        context = ssl._create_unverified_context()

        req = Request(url)

        try:
            n = netrc.netrc()
            login, unused, password = n.authenticators(urlparse(url).hostname)
            add_basic_auth("%s:%s" % (login, password), req)
        except (TypeError, ImportError, IOError, netrc.NetrcParseError):
            pass

        # If url returns 404 or similar, raise exception
        urlopen(req, timeout=20, context=context)
        return True
    except Exception as e:
        print(e)
        print('Error trying to access %s' % url)
        return False

def ftp_useradd(device):
    """Add ftp user to client list to grant access

    :param device: Linux device(lan/wan)
    :type device: Object
    :return: None if client already exists,
             True if "failed" is present in device.before else False
    :rtype: Boolean or None
    """
    device.sendline("useradd -m client -s /usr/sbin/nologin")
    index = device.expect(['already exists'] + [] + device.prompt, timeout=10)
    if index != 0:
        device.sendline("passwd client")
        device.expect("Enter new UNIX password:", timeout=10)
        device.sendline("client")
        device.expect("Retype new UNIX password:", timeout=10)
        device.sendline("client")
        device.expect(device.prompt, timeout=10)
        device.sendline("echo \"/usr/sbin/nologin\" >> /etc/shells")
        device.expect(device.prompt, timeout=10)
        device.sendline("echo \"client\" | tee -a /etc/vsftpd.userlist")
        device.expect(device.prompt, timeout=10)
        device.sendline("chmod 777 /home/client")
        device.expect(device.prompt, timeout=10)
        device.sendline("service vsftpd restart")
        device.expect(device.prompt, timeout=90)
        return "failed" in device.before

def ftp_file_create_delete(device, create_file=None, remove_file=None):
    """create and delete ftp file for upload and download

    :param device: Linux device(lan/wan)
    :type device: Object
    :param create_file: Flag to create file, can be anything except 0, defaults to None
    :type create_file: any , Optional
    :param remove_file: Flag to remove file, can be anything except 0, defaults to None
    :type remove_file: any , Optional
    """
    if create_file:
        device.sendline("dd if=/dev/zero of=%s.txt count=5M bs=1" % create_file)
        device.expect([r"\d{6,8}\sbytes"] + device.prompt, timeout=90)
        device.expect(device.prompt, timeout=10)
    if remove_file:
        device.sendline("rm %s.txt" % remove_file)
        device.expect(device.prompt, timeout=10)

def ftp_device_login(device, ip_mode, device_ip):
    """Login to FTP device by creating credentials

    :param device: Linux device(lan/wan)
    :type device: Object
    :param ip_mode: ipv4 or ipv6
    :type ip_mode: String
    :param device_ip: ip address of destination device(lan/wan)
    :type device_ip: String
    """
    match = re.search(r"(\d)", str(ip_mode))
    value = match.group()
    device.sendline("ftp -%s %s" % (value, device_ip))
    device.expect("Name", timeout=10)
    device.sendline("client")
    device.expect("Password:", timeout=10)
    device.sendline("client")
    device.expect(['230 Login successful'], timeout=10)
    device.expect("ftp>", timeout=10)

def ftp_upload_download(device, ftp_load):
    """Upload or download file

    :param device: Linux device(lan/wan)
    :type device: Object
    :param ftp_load: "download" or "upload"
    :type ftp_load: String
    """

    if "download" in str(ftp_load):
        device.sendline("get %s.txt" % ftp_load)
    elif "upload" in str(ftp_load):
        device.sendline("put %s.txt" % ftp_load)
    device.expect("226 Transfer complete.", timeout=60)
    device.sendline()
    device.expect("ftp>", timeout=10)

def ftp_close(device):
    """Closing the FTP connection

    :param device: Linux device(lan/wan)
    :type device: Object
    """
    device.sendcontrol('c')
    index = device.expect(['>'] + device.prompt, timeout=20)
    if index == 0:
        device.sendline("quit")
        device.expect(device.prompt, timeout=10)

def postfix_install(device):
    """Add eth0 ip to hosts and Install postfix service if not present
    Postfix is a free and open-source mail transfer agent that routes and delivers electronic mail.

    :param device: lan or wan
    :type device: Object
    """
    if retry_on_exception(device.get_interface_ipaddr, ("eth0",), retries=1):
        device.check_output("sed '/'%s'*/d' /etc/hosts > /etc/hosts" % device.get_interface_ipaddr("eth0"))
    install_postfix(device)

def http_service_kill(device, process):
    """Method to kill the existing http service

    :param device: lan or wan
    :type device: Object
    :param process: http or https
    :type process: String
    """
    for i in range(3):
        device.sendcontrol('c')
        device.expect_prompt()
    device.sendline("ps -elf | grep %s" % process)
    device.expect_prompt()
    match = re.search(r".*\s+root\s+(\d+)\s+.*python.*SimpleHTTP", device.before)
    if match:
        device.sendline("kill -9 %s" % match.group(1))
        device.expect_prompt()

def check_prompts(device_list):
    """check to verify prompt of devices.In order to ensure, that all processes were killed by previous
    test, before running a new test.

    :param device_list: List of devices to check
    :type device: List
    """
    for dev in device_list:
        assert "FOO" in dev.check_output('echo "FOO"'), "Failed to validate prompt for device: {}".format(dev.name)
    return True

def hex_to_datetime(output):
    """Convert hexstring format to datettime

    :param output: output of the snmp output
    :type output: hexstring
    """
    out = output.replace('0x','')
    mib_Hex = [out[i:i+2] for i in range(0, len(out), 2)]
    dt = datetime(*list(map(lambda x: int(x, 16), [mib_Hex[0]+mib_Hex[1]]+mib_Hex[2:])))
    return dt

def openssl_verify(device, ip_address, port, options=""):
    """Openssl verfication for SMTP

    :param device: device in which the command has to be excuted
    :type device: device
    :param ip_address: ip address to be connected
    :type ip_address: string
    :param port: port number for the protocol
    :type port: integer
    :param options: extra options, defaults to ""
    :type options: string, optional
    :return: True or False
    :rtype: Boolean
    """
    output = False
    device.sendline("openssl s_client -connect [{}]:{} {}".format(ip_address, port, options))
    if device.expect(["CONNECTED", pexpect.TIMEOUT]) == 0:
        output = True
    try:
        device.expect_prompt()
    except:
        for i in range(3):
            device.sendcontrol('c')
            device.expect_prompt()
    return output
