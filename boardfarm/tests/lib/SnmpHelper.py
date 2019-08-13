# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import json

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
        mibCompiler.compile(*mib_list)

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
                    print("adding %s:{%s}" %(k, v))
                self.mib_dict[k] = v
        if "yy" in self.dbg:
            print(json.dumps(self.mib_dict, indent=4))

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
                print("ERROR: mib \'%s\' not found"%mib_name)
            pass
        return oid.encode('ascii','ignore')

##############################################################################################

if __name__ == '__main__':

    import sys
    class SnmpMibsUnitTest(object):
        """
        Unit test for the SnmpMibs class to be run as a standalone module
        DEBUG:
            BFT_DEBUG=y     shows the compiled dictionary
            BFT_DEBUG=yy    VERY verbose, shows the compiled dictionary and
                            mibs/oid details
        """

        mibs = ['docsDevSwAdminStatus',
                'snmpEngineMaxMessageSize',
                'docsDevServerDhcp',
                'ifCounterDiscontinuityTime',
                'docsBpi2CmtsMulticastObjects',
                'docsDevNmAccessIp']

        mib_files      = ['DOCS-CABLE-DEVICE-MIB', 'DOCS-IETF-BPI2-MIB'] # this is the list of mib/txt files to be compiled
        srcDirectories = ['../../'] # this needs to point to the mibs directory location
        snmp_obj       = None  # will hold an instance of the  SnmpMibs class

        def __init__(self,mibs_location=None, files=None, mibs=None, err_mibs=None):
            """
            Takes:
                mibs_location:  where the .mib files are located (can be a list of dirs)
                files:          the name of the .mib/.txt files (without the extension)
                mibs:           e.g. sysDescr, sysObjectID, etc
                err_mibs:       wrong mibs (just for testing that the compiler rejects invalid mibs)
            """

            # where the .mib files are located
            if mibs_location:
                self.srcDirectories = mibs_location

            if type(self.srcDirectories) != list:
                self.srcDirectories = [self.srcDirectories]

            for d in self.srcDirectories:
                if not os.path.exists(str(d)):
                    msg = 'No mibs directory {} found test_SnmpHelper.'.format(str(self.srcDirectories))
                    raise Exception(msg)

            if files:
                self.mib_files = files

            self.snmp_obj = SnmpMibs(self.mib_files, self.srcDirectories)

            if mibs:
                self.mibs = mibs

            if type(self.mibs) != list:
                self.mibs = [self.mibs]

        def unitTest(self):
            """
            Compiles the ASN1 and gets the oid of the given mibs
            Asserts on failure
            """

            if 'y' in self.snmp_obj.dbg:
                print(self.snmp_obj.mib_dict)
                for k in self.snmp_obj.mib_dict:
                    print(k, ":", self.snmp_obj.mib_dict[k])

            print("Testing get mib oid")

            for i in self.mibs:
                oid = self.snmp_obj.get_mib_oid(i)
                print('mib: %s - oid=%s' % (i, oid))

            return True

    # this section can be used to test the classes above
    # (maybe by redirecting the output to a file)
    # BUT for this to run as a standalone file, it needs an
    # absolute import (see the file import section)

    location = None

    if len(sys.argv) < 3:
        if len(sys.argv) == 1:
            print("Using default values from unit test: %s"%(SnmpMibsUnitTest.srcDirectories))
        else:
            print("Usage:\n%s <path_to_global_mibs>  [<path_to_vendor_mibs>]"%sys.argv[0])
            sys.exit(1)
    else:
        print('sys.argv='+str(sys.argv))
        location = sys.argv

    unit_test = SnmpMibsUnitTest(mibs_location=location)
    assert (unit_test.unitTest())

    print('Done.')
