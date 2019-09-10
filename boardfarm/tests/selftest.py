import rootfs_boot
from boardfarm import lib
import hashlib
import random
import string
import os
import tempfile
from boardfarm.lib import SnmpHelper

from devices import board, wan, lan, wlan, common

'''
    This file can bu used to add unit tests that
    tests/validate the behavior of new/modified
    components.
'''

class selftest_test_copy_file_to_server(rootfs_boot.RootFSBootTest):
    '''
    Copy a file to /tmp on the WAN device using common.copy_file_to_server
    '''
    def runTest(self):
        if not wan:
            msg = 'No WAN Device defined, skipping copy file to WAN test.'
            lib.common.test_msg(msg)
            self.skipTest(msg)

        if not hasattr(wan, 'ipaddr'):
            msg = 'WAN device is not running ssh server, can\'t copy with this function'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        text_file = tempfile.NamedTemporaryFile()
        self.fname = fname = text_file.name

        letters = string.ascii_letters
        fcontent = ''.join(random.choice(letters) for i in range(50))

        text_file.write(fcontent)
        text_file.flush()

        fmd5 = hashlib.md5(open(fname,'rb').read()).hexdigest()
        print("File orginal md5sum: %s"% fmd5)

        wan_ip = wan.get_interface_ipaddr("eth0")

        cmd = "cat %s | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -x %s@%s \"cat - > %s\""\
              % (fname, wan.username, wan_ip, fname)
        # this must fail as the command does not echo the filename
        try:
            common.copy_file_to_server(cmd, wan.password, "/tmp")
        except:
            print("Copy failed as expected")
            pass

        cmd = "cat %s | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -x %s@%s \"cat - > %s; echo %s\""\
              % (fname, wan.username, wan_ip, fname, fname)
        # this should pass
        try:
            common.copy_file_to_server(cmd, wan.password, "/tmp")
        except:
            assert 0,"copy_file_to_server failed, Test failed!!!!"

        # is the destination file identical to the source file
        wan.sendline("md5sum %s"% fname)
        wan.expect(fmd5)
        wan.expect(wan.prompt)

        print("Test passed")

class selftest_test_create_session(rootfs_boot.RootFSBootTest):
    '''
    tests the create_session function in devices/__init__.py
    '''
    session = None
    def runTest(self):
        if not wan:
            msg = 'No WAN Device defined, skipping test_create_session.'
            lib.common.test_msg(msg)
            self.skipTest(msg)

        wan_ip = wan.get_interface_ipaddr("eth0")

        import devices
        # this should fail, as "DebianBoxNonExistent" is not (yet) a device
        try:
            kwargs ={
                    'name':"wan_test_calls_fail",
                    'ipaddr':wan_ip,
                    'port':22,
                    'color': 'magenta'
                    }
            self.session = devices.get_device("DebianBoxNonExistent", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on wrong class name"
            print("Failed to create session on wrong class name (expected) PASS")

        # this must fail, as "169.254.12.18" is not a valid ip
        try:
            kwargs ={
                    'name':"wan_test_ip_fail",
                    'ipaddr':"169.254.12.18",
                    'port':22,
                    'color': 'cyan'
                    }
            self.session = devices.get_device("DebianBox", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on wrong IP"
            print("Failed to create session on wrong IP (expected) PASS")

        # this must fail, as 50 is not a valid port
        try:
            kwargs ={
                    'name':"wan_test_port_fail",
                    'ipaddr':wan_ip,
                    'port':50,
                    'color': 'red'
                    }
            self.session = devices.get_device("DebianBox", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on wrong port"
            print("Failed to create session on wrong port (expected) PASS")

        # this must fail, close but no cigar
        try:
            kwargs ={
                    'name':"wan_test_type_fail",
                    'ipaddr':wan_ip,
                    'port':50,
                    'color': 'red'
                    }
            self.session = devices.get_device("debina", **kwargs)
        except:
            pass
        else:
            assert self.session is None,"Test Failed on misspelled class name"
            print("Failed to create session on misspelled class name (expected) PASS")

        # this should pass
        try:
            kwargs ={
                    'name':"correct_wan_parms",
                    'ipaddr':wan_ip,
                    'port':'22',
                    'color': 'yellow'
                    }
            self.session = devices.get_device("debian", **kwargs)
        except:
            assert 0, "Failed to create session, Test FAILED!"
        else:
            assert self.session is not None,"Test Failed on correct paramters!!"

        print("Session created successfully")

        # is the session really logged onto the wan?

        wan.sendline()
        wan.expect(wan.prompt)
        wan.sendline("ip a")
        wan.expect_exact("ip a")
        wan.expect(wan.prompt)
        w = wan.before

        self.session.sendline()
        self.session.expect(self.session.prompt)
        self.session.sendline("ip a")
        self.session.expect_exact("ip a")
        self.session.expect(self.session.prompt)
        s = self.session.before

        assert w == s, "Interfaces differ!!! Test Failed"

        self.session.sendline("exit")

        print("Test passed")

    def recover(self):
        if self.session is not None:
            self.session.sendline("exit")

class selftest_testing_linuxdevice_functions(rootfs_boot.RootFSBootTest):
    '''
    tests the linux functions moved to devices/linux.py
    '''
    def runTest(self):
        from devices import lan, debian, linux
        if lan.model == "debian":
            # check that lan is derived from LinuxDevice
            assert(issubclass(debian.DebianBox, linux.LinuxDevice))

        #get the mac address of the interface
        lan_mac = lan.get_interface_macaddr(lan.iface_dut)
        assert lan_mac != None, "Failed getting lan mac address"
        print("lan mac address: %s" % lan_mac)

        #check the system uptime
        uptime = lan.get_seconds_uptime()
        assert uptime != None, "Failed getting system uptime"
        print("system uptime is: %s" % uptime)

        #ping ip using function ping from linux.py
        ping_check = lan.ping("8.8.8.8")
        print("ping status is %s" % ping_check)

        #disable ipv6
        lan.disable_ipv6(lan.iface_dut)
        #enable ipv6
        lan.enable_ipv6(lan.iface_dut)
        board.set_printk()
        print("Test passed")

        #remove neighbour table entries
        lan.ip_neigh_flush()

        #set the link state up
        lan.set_link_state(lan.iface_dut, "up")

        #Checking the interface status
        link = lan.is_link_up(lan.iface_dut)
        assert link != None, "Failed to check the link is up"

        #add sudo when the username is root
        lan.sudo_sendline("ping -c5 '8.8.8.8'")
        lan.expect(lan.prompt, timeout=50)

        #add new user name in linux
        lan.add_new_user("test", "test")
        lan.sendline("userdel test")
        lan.expect(lan.prompt)

        text_file = tempfile.NamedTemporaryFile()
        letters = string.ascii_letters
        fcontent = ''.join(random.choice(letters) for i in range(50))

        text_file.write(fcontent)
        text_file.flush()

        fmd5 = hashlib.md5(open(text_file.name, 'rb').read()).hexdigest()
        print("File orginal md5sum: %s"% fmd5)
        print('copying file to lan at /tmp/dst.txt')
        lan.copy_file_to_server(text_file.name, "/tmp/dst.txt")
        print('Copy Done. Verify the integrity of the file')
        lan.sendline('md5sum /tmp/dst.txt')
        lan.expect(fmd5)
        lan.expect(lan.prompt)

        '''FUnctions moved from openwrt to linux '''
        #Wait until network interfaces have IP Addresses
        board.wait_for_network()
        print "Waited until network interfaces has ip address"

        #Check the available memory of the device
        memory_avail = board.get_memfree()
        print 'Available memory of the device:{}'.format(memory_avail)

        #Getting the vmstat
        vmstat_out = board.get_proc_vmstat()
        assert vmstat_out is not None, 'virtual machine status is None'
        print "Got the vmstat{}".format(vmstat_out)

        #Get the total number of connections in the network
        nw_count = board.get_nf_conntrack_conn_count()
        assert nw_count is not None , 'connections are empty'
        print 'Get the total number of connections in the network{}'.format(nw_count)

        #Getting the DNS server upstream
        ip_addr = board.get_dns_server_upstream()
        assert ip_addr is not None, 'Getting nameserver ip is None'
        print "Got the DNS server upstream{}".format(ip_addr)
        print('Test Passed')

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
    error_mibs = ['SsnmpEngineMaxMessageSize', # mispelled MUST fail
                  'nonExistenMib',             # this one MUST fail
                  'ifCounterDiscontinuityTimeQ']  # mispelled MUST fail

    mibs = ['docsDevSwAdminStatus',
            'snmpEngineMaxMessageSize',
            error_mibs[0],
            'docsDevServerDhcp',
            'ifCounterDiscontinuityTime',
            error_mibs[1],
            'docsBpi2CmtsMulticastObjects',
            error_mibs[2]]

    mib_files      = ['DOCS-CABLE-DEVICE-MIB', 'DOCS-IETF-BPI2-MIB'] # this is the list of mib/txt files to be compiled
    srcDirectories = ['/tmp/boardfarm-docsis/mibs'] # this needs to point to the mibs directory location
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

        self.snmp_obj = SnmpHelper.SnmpMibs(self.mib_files, self.srcDirectories)

        if mibs:
            self.mibs = mibs
            self.error_mibs = err_mibs

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
            try:
                oid = self.snmp_obj.get_mib_oid(i)
                print('mib: %s - oid=%s' % (i, oid))
            except Exception:
                #we shoudl NOT find only the errored mibs, all other mibs MUST be found
                assert(i in self.error_mibs), "Failed to get oid for mib: " + i
                print("Failed to get oid for mib: %s (expected)" % i)
                if (self.error_mibs is not None):
                    self.error_mibs.remove(i)

        # the unit test must find all the errored mibs!
        if (self.error_mibs is not None):
            assert (self.error_mibs == []), "The test missed the following mibs: %s"%str(self.error_mibs)
        return True

class selftest_test_SnmpHelper(rootfs_boot.RootFSBootTest):
    '''
    Tests the SnmpHelper module:
    1. compiles and get the oid of some sample mibs
    2. performs an snmp get from the lan to the wan
       using hte compiled oids
    '''

    def runTest(self):

        from boardfarm.lib.installers import install_snmp, install_snmpd
        from boardfarm.lib.common import snmp_mib_get

        wrong_mibs = ['PsysDescr', 'sys123ObjectID', 'sysServiceS']
        linux_mibs = ['sysDescr',\
                      'sysObjectID',\
                      'sysServices',\
                      'sysName',\
                      'sysServices',\
                      'sysUpTime']

        test_mibs = [linux_mibs[0], wrong_mibs[0],\
                     linux_mibs[1], wrong_mibs[1],\
                     linux_mibs[2], wrong_mibs[2]]


        unit_test = SnmpMibsUnitTest(mibs_location = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                                     os.pardir,
                                                                     'resources',
                                                                     'mibs')),
                                     files = ['SNMPv2-MIB'],
                                     mibs = test_mibs,
                                     err_mibs = wrong_mibs)
        assert (unit_test.unitTest())

        install_snmpd(wan)

        lan.sendline('echo "nameserver 8.8.8.8" >> /etc/resolv.conf')
        lan.expect(lan.prompt)

        install_snmp(lan)
        wan_iface_ip = wan.get_interface_ipaddr(wan.iface_dut)

        for mib in linux_mibs:
            try:
                result = snmp_mib_get(lan,
                                      unit_test.snmp_obj,
                                      str(wan_iface_ip),
                                      mib,
                                      '0',
                                      community='public')

                print('snmpget({})@{}={}'.format(mib, wan_iface_ip, result))
            except Exception as e:
                print('Failed on snmpget {} '.format(mib))
                print(e)
                raise e

        print("Test passed")
