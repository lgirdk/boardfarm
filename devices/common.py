# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import binascii
import os
import pexpect
import sys
import urllib2

import termcolor

def get_file_magic(fname, num_bytes=4):
    '''Return the first few bytes from a file to determine the type.'''
    if fname.startswith("http://") or fname.startswith("https://"):
        rng = 'bytes=0-%s' % (num_bytes-1)
        req = urllib2.Request(fname, headers={'Range': rng})
        data = urllib2.urlopen(req).read()
    else:
        f = open(fname, 'rb')
        data = f.read(num_bytes)
        f.close()
    return binascii.hexlify(data)

def copy_file_to_server(cmd, password):
    '''Requires a command like ssh/scp to transfer a file, and a password.
    Run the command and enter the password if asked for one.'''
    for attempt in range(5):
        try:
            print_bold(cmd)
            p = pexpect.spawn(command='/bin/bash', args=['-c', cmd], timeout=240)
            p.logfile_read = sys.stdout

            i = p.expect(["yes/no", "password:", "/tftpboot/.*"])
            if i == 0:
                    p.sendline("yes")
                    i = p.expect(["not used", "password:", "/tftpboot/.*"], timeout=45)

            if i == 1:
                    p.sendline("%s" % password)
                    p.expect("/tftpboot/.*", timeout=120)

            fname = p.match.group(0).strip()
            print_bold("\nfile: %s" % fname)
        except Exception as e:
            print_bold(e)
            print_bold("tried to copy file to server and failed!")
        else:
            return fname[10:]

        print_bold("Unable to copy file to server, exiting")
        raise Exception("Unable to copy file to server")

def download_from_web(url, server, username, password, port):
    cmd = "curl -n -L -k '%s' 2>/dev/null | ssh -p %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -x %s@%s \"mkdir -p /tftpboot/tmp; tmpfile=\`mktemp /tftpboot/tmp/XXXXX\`; cat - > \$tmpfile; chmod a+rw \$tmpfile; echo \$tmpfile\"" % (url, port, username, server)
    return copy_file_to_server(cmd, password)

def scp_to_tftp_server(fname, server, username, password, port):
    # local file verify it exists first
    if not os.path.isfile(fname):
        print_bold("File passed as parameter does not exist! Failing!\n")
        sys.exit(10)

    cmd = "cat %s | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p %s -x %s@%s \"mkdir -p /tftpboot/tmp; tmpfile=\`mktemp /tftpboot/tmp/XXXXX\`; cat - > \$tmpfile; chmod a+rw \$tmpfile; echo \$tmpfile\"" % (fname, port, username, server)
    return copy_file_to_server(cmd, password)

def print_bold(msg):
    termcolor.cprint(msg, None, attrs=['bold'])
