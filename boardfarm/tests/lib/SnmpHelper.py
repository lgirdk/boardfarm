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
        print('sys.argv='+sys.argv)
        location = sys.argv

    unit_test = SnmpMibsUnitTest(mibs_location=location)
    assert (unit_test.unitTest())

    print('Done.')
