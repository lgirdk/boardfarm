# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import os, config
from common import cmd_exists
import Tkinter
import re
import time
import hashlib

class docsis:
    """
    Name: docsis module
    Purpose: docsis operating.
    Input: Absolute path of text file
    Fuction:
        decode():
            return output file name(.txt)
        encode(output_type='cm_cfg')
            return output file name(.cfg or .bin)
    """

    mibs_path_arg = ""
    def __init__(self, file_or_obj, tmpdir=None, mibs_paths=None):
        # TODO: fix at some point, this tmpdir is already relative to the CM config you
        # are grabbing? Not ideal as that dir might not be writeable, or a tftp or http URL
        # at some point - need to use a real local tmpdir or maybe even results so we can
        # save the resulting artifacts in other tools
        if tmpdir is None:
            tmpdir = os.path.join('tmp', config.board['station'])

        from devices import board
        if mibs_paths is None and hasattr(board, 'mibs_paths'):
            default = os.path.expandvars('/home/$USER/.snmp/mibs:/usr/share/snmp/mibs:/usr/share/snmp/mibs/iana:/usr/share/snmp/mibs/ietf:/usr/share/mibs/site:/usr/share/snmp/mibs:/usr/share/mibs/iana:/usr/share/mibs/ietf:/usr/share/mibs/netsnmp')
            mibs_path_arg = "-M "  + default

            for mibs_path in board.mibs_paths:
                mibs_path_arg = mibs_path_arg + ":" + mibs_path

            self.mibs_path_arg = mibs_path_arg

        # TODO: this is all a bit wild here, need to clean up everything..
        if isinstance(file_or_obj, cm_cfg):
            self.cm_cfg = file_or_obj
            # TODO: this seems like the wrong place to store these but OK
            self.dir_path=os.path.join(os.path.split(__file__)[0], tmpdir)
            self.file = self.cm_cfg.original_fname
            self.file_path = os.path.join(self.dir_path, self.file)
        else:
            self.file_path=file_or_obj
            self.dir_path=os.path.join(os.path.split(file_or_obj)[0], tmpdir)
            self.file=os.path.split(file_or_obj)[1]

        # make target tmpdir if it does not exist
        try:
            os.makedirs(self.dir_path)
        except OSError, err:
            import errno
            # Reraise the error unless it's about an already existing directory
            if err.errno != errno.EEXIST or not os.path.isdir(self.dir_path):
                raise

        if isinstance(file_or_obj, cm_cfg):
            self.cm_cfg.save(self.file_path)

        assert cmd_exists('docsis')
        assert cmd_exists('tclsh')
        tclsh = Tkinter.Tcl()
        assert tclsh.eval("package require sha1"), "please run apt-get install tcllib first"

    def decode(self):
        if '.cfg' in self.file:
            os.system("docsis -d %s > %s" %(self.file_path, self.file_path.replace('.cfg', '.txt')))
            assert os.path.exists(self.file.replace('.cfg', '.txt'))

            return  self.file.replace('.cfg', '.txt')

        # TODO: decode MTA?

    def encode(self, output_type='cm_cfg'):
        def encode_mta():
            mtacfg_name=self.file.replace('.txt', '.bin')
            mtacfg_path=os.path.join(self.dir_path, mtacfg_name)
            if os.path.isfile(mtacfg_path):
                os.remove(mtacfg_path)
            tclsh = Tkinter.Tcl()
            tclsh.eval("source %s/mta_conf_Proc.tcl" % os.path.dirname(__file__))
            tclsh.eval("run [list %s -e -hash eu -out %s]" % (self.file_path, mtacfg_path))
            assert os.path.exists(mtacfg_path)

            return mtacfg_path

        def encode_cm():
            cmcfg_name=self.file.replace('.txt', '.cfg')
            cmcfg_path=os.path.join(self.dir_path, cmcfg_name)
            if os.path.isfile(cmcfg_path):
                os.remove(cmcfg_path)
            print("docsis %s -e %s /dev/null %s" % (self.mibs_path_arg, self.file_path, cmcfg_path))
            os.system("docsis %s -e %s /dev/null %s" % (self.mibs_path_arg, self.file_path, cmcfg_path))
            assert os.path.exists(cmcfg_path)

            return cmcfg_path

        if output_type == 'mta_cfg':
            return encode_mta()

        # default is CM cfg, if that fails we try to use special mta tool
        try:
            return encode_cm()
        except:
            return encode_mta()

class cm_cfg(object):
    '''
    Class for generating CM cfg from nothing, or even importing from a file
    They later need to be encoded via a compiler
    '''

    # TODO: all these names will need to be made up once we don't have
    # an input file anymore
    original_fname = None
    original_file = None
    encoded_suffix = '.cfg'
    encoded_fname = None

    # string representation of cm cfg
    # temporary for starting point
    txt = ""

    # plenty of tests reference a file name, and assume it's in a certain
    # place so let's allow for that for now
    legacy_search_path = None

    def __init__(self, start=None):
        '''Creates a default basic CM cfg file for modification'''

        # TODO: we require loading a file for the moment
        if start == None:
            raise Exception("We don't know how to start from scratch yet")
        else:
            # TODO: filename should not matter
            self.original_file = start
            self.original_fname = os.path.split(start)[1]
            self.encoded_fname = self.original_fname.replace('.txt', self.encoded_suffix)
            self.load(start)

    def load(self, cm_txt):
        '''Load CM cfg from txt file, for modification'''

        if self.legacy_search_path is not None:
            cm_txt = os.path.join(self.legacy_search_path, cm_txt)

        with open(cm_txt, 'r') as txt:
            self.txt = txt.read()

    def __str__(self):
        '''String repr of CM txt'''
        return self.txt

    def shortname(self):
        '''short name for displaying in summary'''
        return hashlib.md5(self.txt.encode()).hexdigest()

    def save(self, full_path):
        with open(full_path, 'w') as txt:
            txt.write(self.txt)

    def generic_re_sub(self, regex, sub):
        '''Crude function to replace strings in configs, should be replaced with subclasses'''
        saved_txt = self.txt

        self.txt = re.sub(regex, sub, self.txt)

        if saved_txt == self.txt:
            print("WARN: no regex sub was made for %s, to be replaced with %s" % (regex, sub))

    def _cm_configmode(self):
        '''function to check config mode in CM'''
        '''0-Disable/Bridge, 1-IPv4, 2-IPv6 (DSlite), 3-IPv4 and IPv6(Dual)'''
        modeset = ['0x010100', '0x010101', '0x010102', '0x010103']
        modestr = ['bridge', 'ipv4', 'dslite', 'dual-stack']
        for mode in range(0, len(modeset)):
            tlv_check = "GenericTLV TlvCode 202 TlvLength 3 TlvValue "+modeset[mode]
            initmode_check = "InitializationMode "+str(mode)
            if (tlv_check in self.txt) or (initmode_check in self.txt):
                return modestr[mode]

    cm_configmode = property(_cm_configmode)

class mta_cfg(cm_cfg):
    '''MTA specific class for cfgs'''

    encoded_suffix = '.bin'

def check_valid_docsis_ip_networking(board, strict=True, time_for_provisioning=120):
    start_time = time.time()

    wan_ipv4 = False
    wan_ipv6 = False
    erouter_ipv4 = False
    erouter_ipv6 = False
    mta_ipv4 = True
    mta_ipv6 = False # Not in spec

    cm_configmode = board.cm_cfg.cm_configmode

    if cm_configmode == 'bridge':
        # TODO
        pass
    if cm_configmode == 'ipv4':
        wan_ipv4 = erouter_ipv4 = True
    if cm_configmode == 'dslite':
        # TODO
        pass
    if cm_configmode == 'dual-stack':
        wan_ipv4 = erouter_ipv4 = True
        wan_ipv6 = erouter_ipv6 = True

    while (time.time() - start_time < time_for_provisioning):
        try:
            if wan_ipv4:
                valid_ipv4(board.get_interface_ipaddr(board.wan_iface))
            if wan_ipv6:
                valid_ipv6(board.get_interface_ip6addr(board.wan_iface))

            if hasattr(board, 'erouter_iface'):
                if erouter_ipv4:
                    valid_ipv4(board.get_interface_ipaddr(board.erouter_iface))
                if erouter_ipv6:
                    valid_ipv6(board.get_interface_ip6addr(board.erouter_iface))

            if hasattr(board, 'mta_iface'):
                if mta_ipv4:
                    valid_ipv4(board.get_interface_ipaddr(board.mta_iface))
                if mta_ipv6:
                    valid_ipv6(board.get_interface_ip6addr(board.mta_iface))

            # if we get this far, we have all IPs and can exit while loop
            break
        except KeyboardInterrupt:
            raise
        except:
            if time.time() - start_time > time_for_provisioning:
                if strict:
                    assert False, "Failed to provision docsis device properly"
                else:
                    print("WARN: failed to provision board entirely")
