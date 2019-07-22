# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import json
import re


if __name__ == '__main__':
    # this allows it to run as a standalone module (i.e. python tests/lib/SnmpHelper.py)
    # forces the import of the global logging not the local one
    # for this part to be removed we need to rename the local logging.py
    # or move this module elsewhere
    import sys
    sys.path.insert(0, '/usr/lib/python2.7/')
    import logging

from pysmi.reader import FileReader, HttpReader
from pysmi.searcher import StubSearcher
from pysmi.writer import CallbackWriter
from pysmi.parser import SmiStarParser
from pysmi.codegen import JsonCodeGen
from pysmi.compiler import MibCompiler

class SnmpMibs(object):
    """
    Look up specific ASN.1 MIBs at configured Web and FTP sites,
    compile them into JSON documents and print them out to stdout.
    Try to support both SMIv1 and SMIv2 flavors of SMI as well as
    popular deviations from official syntax found in the wild.
    Source:
    http://snmplabs.com/pysmi/examples/download-and-compile-smistar-mibs-into-json.html

    DEBUG:
        BFT_DEBUG=y     shows which mib module is being parsed
        BFT_DEBUG=yy    VERY verbose, shows the compiled dictionary and
                        mibs/oid details
    """
    dbg = None
    mib_dict = {}

    def __init__(self, mib_list, src_dir_list, http_sources=None):
        if "BFT_DEBUG" in os.environ:
            self.dbg = os.environ.get('BFT_DEBUG')
        else:
            self.dbg = ""

        if "yy" in self.dbg:
            # VERY verbose, but essential for spotting
            # possible  ASN.1 errors
            from pysmi import debug
            debug.setLogger(debug.Debug('reader', 'compiler'))

        # Initialize compiler infrastructure
        mibCompiler = MibCompiler(
            SmiStarParser(), JsonCodeGen(), CallbackWriter(self.callback_func)
        )

        # search for source MIBs here
        mibCompiler.addSources(*[FileReader(x) for x in src_dir_list])

        if http_sources:
            # search for source MIBs at Web sites
            mibCompiler.addSources(*[HttpReader(*x) for x in http_sources])

        # never recompile MIBs with MACROs
        mibCompiler.addSearchers(StubSearcher(*JsonCodeGen.baseMibs))

        # run recursive MIB compilation
        results = mibCompiler.compile(*mib_list)

    def callback_func(self, mibName, jsonDoc, cbCtx):
        if "y" in self.dbg:
            print('# MIB module %s' % mibName)

        for k,v in json.loads(jsonDoc).iteritems():
            if "oid" in v:
                if "objects" in v or "revisions" in v:
                    # we want to skip objects that have no use
                    continue
                # add it to my dict
                if "yy" in self.dbg:
                    print "adding %s:{%s}" %(k, v)
                self.mib_dict[k] = v
        if "yy" in self.dbg:
            print (json.dumps(self.mib_dict, indent=4))

    def get_dict_mib(self):
        return self.mib_dict

    def get_mib_oid(self, mib_name):
        """
        Given a mib name, returns the OID, None if not found
        """
        oid = None
        try:
            oid = self.mib_dict[mib_name]['oid']
        except:
            if  "y" in self.dbg:
                print "ERROR: mib \'%s\' not found"%mib_name
            pass
        return oid.encode('ascii','ignore')


class SnmpMibsUnitTest(object):
    """
    Unit test for the SnmpMibs class.
    Check for correct and incorrect mibs.
    Default assumes the .mib files are in $USER/.snmp
    DEBUG:
        BFT_DEBUG=y     shows the compiled dictionary
        BFT_DEBUG=yy    VERY verbose, shows the compiled dictionary and
                        mibs/oid details
    """
    error_mibs = ['1emtaEndPntConfigPulseDialMinMakeTime1', # mispelled MUST fail
                  'nonExistenMib', # this one MUST fail
                  'docsBpi2LKMasCmtsMulticastObjects']  # mispelled MUST fail

    mibs = ['docsDevSwAdminStatus',
            'emtaEndPntConfigPulseDialMinMakeTime',
            error_mibs[0],
            'emtaCallHistoryJitter',
            'pktcSigDevCIDFskAfterRing',
            error_mibs[1],
            'docsBpi2CmtsMulticastObjects',
            error_mibs[2]]

    mib_files = ['DOCS-CABLE-DEVICE-MIB', 'Main', 'pktcSig-eu', 'DOCS-IETF-BPI2-MIB']
    srcDirectories = os.environ.get('HOME') + '/.snmp/mibs'
    snmp_obj       = None
    dbg            = False

    def __init__(self,mibs_location=None, files=None, mibs=None):
        # where the .mib files are located
        if mibs_location:
            self.srcDirectories = mibs_location

        if not os.path.exists(str(self.srcDirectories)):
            msg = 'No mibs directory {} found test_SnmpHelper.'.format(str(self.srcDirectories))
            raise Exception(msg)

        if files:
            self.mib_files = files

        self.snmp_obj = SnmpMibs(self.mib_files, [self.srcDirectories])

    def unitTest(self):

        if 'y' in self.snmp_obj.dbg:
            print(self.snmp_obj.mib_dict)
            for k in self.snmp_obj.mib_dict:
                print (k, ":", self.snmp_obj.mib_dict[k])

        for i in self.mibs:
            try:
                oid = self.snmp_obj.get_mib_oid(i)
                print 'mib: %s - oid=%s'%(i, oid)
            except Exception as e:
                #we shoudl NOT find only the errored mibs, all other mibs MUST be found
                assert(i in self.error_mibs), "Failed to get oid for mib: " + i
                print "Failed to get oid for mib: %s (expected)"%i
                self.error_mibs.remove(i)

        # the unit test must find all the errored mibs!
        assert (self.error_mibs == []), "The test missed the following mibs: %s"%str(self.error_mibs)
        return True

##############################################################################################

if __name__ == '__main__':

    # this section can be used to test the classes above
    # (maybe by redirecting the output to a file)
    # BUT for this to run as a standalone file, it needs an
    # absolute import (see the file import section)

    location = None

    if len(sys.argv) < 3:
        if len(sys.argv) == 1:
            print "Using default values from unit test: %s"%(SnmpMibsUnitTest.srcDirectories)
        else:
            print "Usage:\n%s <path_to_global_mibs>  [<path_to_vendor_mibs>]"%sys.argv[0]
            sys.exit(1)
    else:
        print 'sys.argv='+sys.argv
        location = sys.argv

    unit_test = SnmpMibsUnitTest(mibs_location=location)
    assert (unit_test.unitTest())

    print 'Done.'
