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

def find_directory_in_tree(pattern, root_dir):
    """
    Looks for all the directories where the name matches pattern
    Avoids paths patterns already in found, i.e.:
    root/dir/pattern (considered)
    root/dir/pattern/dir1/pattern (not considered since already in the path)

    Parameters:
    pattern:  name to match against
    root_dir: root of tree to traverse

    Returns a list of dirs
    """
    dirs_list = []
    for root, dirs, files in os.walk(root_dir):
        for name in dirs:
            if 'mib' in name or 'mibs' in name:
                d = os.path.join(root, name)
                if any(s in d for s in dirs_list):
                    continue
                else:
                    dirs_list.append(d)
    return dirs_list

def find_files_in_tree(root_dir, no_ext=True, no_dup=True, ignore=[]):
    """
    Looks for all the files in a directry tree

    Parameters:
    root_dir: root of tree to traverse, can be a list of directory

    Returns a list of files
    """

    if (type(root_dir) is not list) and len(root_dir):
        root_dir = [root_dir]

    file_list = []

    if len(root_dir):
        for d in root_dir:
            for root, dirs, files in os.walk(d):
                for f in files:
                    if any(map( lambda x: x in f, ignore)):
                        continue
                    if no_ext:
                        f = os.path.splitext(f)[0]
                    file_list.append(f)
        if no_dup:
            file_list = list(dict.fromkeys(file_list))
    return file_list


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

    snmp_parser = None

    @property
    def default_mibs(self):
        return SnmpMibs.get_mib_parser()

    @classmethod
    def get_mib_parser(cls, snmp_mib_files=None, snmp_mib_dirs=None, http_sources=None):

        if cls.snmp_parser is not None:
            return cls.snmp_parser

        if snmp_mib_files is None:
            snmp_mib_files= []

        if snmp_mib_dirs is None:
            snmp_mib_dirs = ['/usr/share/snmp/mibs']

        # looks for the boardfarm directory path
        thisfiledir = os.path.realpath(__file__)
        boardfarmdir = thisfiledir[:thisfiledir.rfind('boardfarm')]

        # add the boardfarm dir as it is not in the overlays
        snmp_mib_dirs.extend(find_directory_in_tree('mibs', boardfarmdir))

        if 'BFT_OVERLAY' in os.environ:
            for overlay in os.environ['BFT_OVERLAY'].split(' '):
                # finds all dirs with the word mibs in it
                # avoid adding a directory that is already
                # contained in the directory tree
                snmp_mib_dirs.extend(find_directory_in_tree('mib', overlay))

            if 'BFT_DEBUG' in os.environ:
                print('Mibs direcotry list: %s' % snmp_mib_dirs)

        # if the mibs file are given, we do not want to add other mibs, as it may
        # results in unresolved ASN.1 imports
        if len(snmp_mib_files) == 0:
            # only traverses the mib dirs and compile all the files
            # /usr/share/snmp/mibs has miblist.txt which MUST be ignored
            snmp_mib_files = find_files_in_tree(snmp_mib_dirs, ignore=['miblist.txt', '__', '.py'])
        if 'BFT_DEBUG' in os.environ:
            print('Mibs file list: %s' % snmp_mib_files)

        # creates the snmp parser object
        cls.snmp_parser = cls(snmp_mib_files, snmp_mib_dirs)
        return cls.snmp_parser

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
        mib_dict = mibCompiler.compile(*mib_list)

        err = False

        if mib_dict is None or mib_dict == {}:
            print("ERROR: failed on mib compilation (mibCompiler.compile returned an empty dictionary)")
            err = True

        for key, value in mib_dict.iteritems():
            if value == 'unprocessed':
                print("ERROR: failed on mib compilation: " + key + ": " + value)
                err = True

        if err:
            raise Exception("SnmpMibs failed to initialize.")
        elif 'BFT_DEBUG' in os.environ:
            print('# %d MIB modules compiled'%len(mib_dict))

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
        test_singleton = False # if True it will invoke get_mib_parser() static method

        mibs = ['docsDevSwAdminStatus',
                'snmpEngineMaxMessageSize',
                'docsDevServerDhcp',
                'ifCounterDiscontinuityTime',
                'docsBpi2CmtsMulticastObjects',
                'docsDevNmAccessIp']

        mib_files      = ['DOCS-CABLE-DEVICE-MIB', 'DOCS-IETF-BPI2-MIB'] # this is the list of mib/txt files to be compiled
        srcDirectories = ['/usr/share/snmp/mibs'] # this needs to point to the mibs directory location
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
                    msg = 'No mibs directory {} found test_SnmpHelper.'.format(str(d))
                    raise Exception(msg)

            if files:
                self.mib_files = files

            if SnmpMibsUnitTest.test_singleton:
                self.snmp_obj = SnmpMibs.get_mib_parser(self.mib_files, self.srcDirectories)
                print("Using class singleton: %r" % self.snmp_obj)
            else:
                self.snmp_obj = SnmpMibs(self.mib_files, self.srcDirectories)
                print("Using object instance: %r" % self.snmp_obj)

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

    if '-h' in sys.argv or '--help' in sys.argv or len(sys.argv) < 2:
        print("Usage:\n%s <path_to_mibs>  [<path_to_mibs> ...]"%sys.argv[0])
        print("\nE.g.: python %s  ../boardfarm-docsis/mibs /usr/share/snmp/mibs "%sys.argv[0])
        sys.exit(1)

    print('sys.argv='+str(sys.argv))
    location = sys.argv[1:]

    SnmpMibsUnitTest.test_singleton = False
    unit_test = SnmpMibsUnitTest(mibs_location=location)
    assert (unit_test.unitTest())

    SnmpMibsUnitTest.test_singleton = True
    unit_test = SnmpMibsUnitTest(mibs_location=location)
    assert (unit_test.unitTest())


    print('Done.')
