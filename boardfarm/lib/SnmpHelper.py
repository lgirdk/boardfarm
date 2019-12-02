# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import json
import pexpect
import six

from .installers import install_pysnmp
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
                    if any(map(lambda x: x in f, ignore)):
                        continue
                    if no_ext:
                        f = os.path.splitext(f)[0]
                    file_list.append(f)
        if no_dup:
            file_list = list(dict.fromkeys(file_list))
    return file_list

class SnmpMibsMeta(type):
        @property
        def default_mibs(self):
            return SnmpMibs.get_mib_parser()

class SnmpMibs(six.with_metaclass(SnmpMibsMeta, object)):
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

    @classmethod
    def get_mib_parser(cls, snmp_mib_files=None, snmp_mib_dirs=None, http_sources=None):

        if cls.snmp_parser is not None:
            return cls.snmp_parser

        if snmp_mib_files is None:
            snmp_mib_files = []

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

        for key, value in mib_dict.items():
            if value == 'unprocessed':
                print("ERROR: failed on mib compilation: " + key + ": " + value)
                err = True

        if err:
            raise Exception("SnmpMibs failed to initialize.")
        elif 'BFT_DEBUG' in os.environ:
            print('# %d MIB modules compiled' % len(mib_dict))

    def callback_func(self, mibName, jsonDoc, cbCtx):
        if "y" in self.dbg:
            print('# MIB module %s' % mibName)

        for k, v in json.loads(jsonDoc).items():
            if "oid" in v:
                if "objects" in v or "revisions" in v:
                    # we want to skip objects that have no use
                    continue
                # add it to my dict
                if "yy" in self.dbg:
                    print("adding %s:{%s}" % (k, v))
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
            if "y" in self.dbg:
                print("ERROR: mib \'%s\' not found" % mib_name)
            pass
        return oid.encode('ascii', 'ignore')

def snmp_v2(device, ip, mib_name, index=0, value=None, timeout=10, retries=3, community="private"):
    """
    Performs an snmp get/set on ip from device's console.
    If value is provided, action = snmpget else action = snmpset

    Parameters:
        (pexpect.spawn) device : device used to perform snmp
        (str) ip : ip address used to perform snmp
        (str) mib_name : mib name used to perform snmp
        (int) index : index used along with mib_name

    Returns:
        (str) result : snmp result
    """

    if not getattr(device, "pysnmp_installed", False):
        install_pysnmp(device)
        setattr(device, "pysnmp_installed", True)

    oid = get_mib_oid(mib_name)

    def _run_snmp(py_set=False):
        action = "setCmd" if py_set else "getCmd"
        pysnmp_cmd = 'cmd = %s(SnmpEngine(), CommunityData("%s"), UdpTransportTarget(("%s", 161), timeout=%s, retries=%s), ContextData(), ObjectType(ObjectIdentity("%s.%s")%s))' % \
                (action, community, ip, timeout, retries, oid, index, ', %s("%s")' % (stype, value) if py_set else "")

        py_steps = [
                'from pysnmp.hlapi import *',
                 pysnmp_cmd,
                'errorIndication, errorStatus, errorIndex, varBinds = next(cmd)',
                'print(errorStatus == 0)',
                'result = varBinds[0][1] if errorStatus == 0 else errorStatus',
                'print(result.prettyPrint())',
                'print(result.__class__.__name__)'
                ]

        device.sendline("cat > snmp.py << EOF\n%s\nEOF" % "\n".join(py_steps))
        device.expect_prompt()
        device.sendline("python snmp.py")
        device.expect_exact("python snmp.py")
        if device.expect(["Traceback", pexpect.TIMEOUT], timeout=3) == 0:
            device.expect_prompt()
            data = False, "Python file error :\n%s" % device.before["\n"][-1].strip(), None
        else:
            device.expect_prompt()
            result = [i.strip() for i in device.before.split('\n') if i.strip() != ""]
            data = result[0] == "True", "\n".join(result[1:-1]), result[-1]
        device.sendline("rm snmp.py")
        device.expect_prompt()
        return data

    status, result, stype = _run_snmp()
    assert status, "SNMP GET Error:\nMIB:%s\nError:%s" % (mib_name, result)

    if value:
        status, result, stype = _run_snmp(True)
        assert status, "SNMP SET Error:\nMIB:%s\nError:%s" % (mib_name, result)

    return result

def get_mib_oid(mib_name):
    """
    Returns the oid for the given mib name.
    Uses the singleton of the SnmpHelper.SnmpMibs class, and instantiate one if none were
    previously created.
    Note: if the singleton is instatiated via this function the overlays are automatically
    scanned for mib files inside ".../mibs/" directories.

    Parameters:
    mib_name    a string (e.g. "sysObjectID", "docsDevSwAdminStatus")
    Returns:
    string      the oid (e.g. "1.3.6.1.2.1.69.1.4.5")
    """
    obj = SnmpMibs.default_mibs
    return obj.get_mib_oid(mib_name)

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
        test_singleton = False  # if True it will invoke get_mib_parser() static method

        mibs = ['docsDevSwAdminStatus',
                'snmpEngineMaxMessageSize',
                'docsDevServerDhcp',
                'ifCounterDiscontinuityTime',
                'docsBpi2CmtsMulticastObjects',
                'docsDevNmAccessIp']

        mib_files = ['DOCS-CABLE-DEVICE-MIB', 'DOCS-IETF-BPI2-MIB']  # this is the list of mib/txt files to be compiled
        srcDirectories = ['/usr/share/snmp/mibs']  # this needs to point to the mibs directory location
        snmp_obj = None  # will hold an instance of the  SnmpMibs class

        def __init__(self, mibs_location=None, files=None, mibs=None, err_mibs=None):
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
        print("Usage:\n%s <path_to_mibs>  [<path_to_mibs> ...]" % sys.argv[0])
        print("\nE.g.: python %s  ../boardfarm-docsis/mibs /usr/share/snmp/mibs " % sys.argv[0])
        sys.exit(1)

    print('sys.argv=' + str(sys.argv))
    location = sys.argv[1:]

    SnmpMibsUnitTest.test_singleton = False
    unit_test = SnmpMibsUnitTest(mibs_location=location)
    assert (unit_test.unitTest())

    SnmpMibsUnitTest.test_singleton = True
    unit_test = SnmpMibsUnitTest(mibs_location=location)
    assert (unit_test.unitTest())


    print('Done.')
