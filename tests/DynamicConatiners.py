import rootfs_boot
from devices import board, wan, lan, get_device, docker_host_vlan, docker_host_direct
from library import print_bold
from lib.regexlib import ValidIpv4AddressRegex
import config
import debian_host
from lib.logging import log_message,logfile_assert_message

class dynamicContainersTest(rootfs_boot.RootFSBootTest):
    """Simple test for the creation of the dynamic containers"""
    dyn_containers_num = 10 # NOTE: per interface
    log_to_file = ""
    cm_erouter_ip = None
    webserver = None
    docker_host = None

    def testSetup(self):
        log_message(self, 'Test Setup', True)

        log_message(self, 'Creates the devices dynamically')

        self.docker_host.spawn_containers(self.dyn_containers_num)

        # total number of containers
        num_containers = self.dyn_containers_num * len(self.docker_host.interfaces)

        logfile_assert_message(self,
                               num_containers == len(self.docker_host.container_list),
                               "Containers created %s/%s"%(self.dyn_containers_num, len(self.docker_host.container_list)))

        log_message(self, 'Test Setup Cmpleted', True)

    def do_test(self):
        log_message(self, 'Testing ' + self.docker_host.name + ' START', True)
        self.testSetup()
        log_message(self, 'Test Execution', True)
        '''
        # arris CMs have no lan<-> wan connectivity YET!!!
        self.cm_erouter_ip = board.get_interface_ipaddr(board.erouter_iface)
        wan.sendline('python -m SimpleHTTPServer 8000')
        wan.expect('Serving HTTP on 0.0.0.0 port 8000', timeout=60)

        for session in docker_host.container_list:
            session.sendline('traceroute %s'% wan.ipaddr)
            session.expect(session.prompt)
            session.sendline('curl http://%s:8000'% wan.ipaddr)
            wan.expect(['%s\s.*GET.*200\s-'% self.cm_erouter_ip])
            session.expect('DOCTYPE html PUBLIC.*/html>')
            session.expect(session.prompt)

        log_message(self, 'killing webserver (a stack trace will appear)')

        wan.sendcontrol('c')
        wan.expect(wan.prompt)
        '''
        self.webserver = None
        # use the first dyn-lan as a web server and the others as we clients
        for idx,session in enumerate(self.docker_host.container_list):
            session.dut_ipaddr = session.get_interface_ipaddr(session.iface_dut)
            if idx == 0:
                self.webserver = session
                self.webserver.ipaddr = session.dut_ipaddr
                self.webserver.sendline('python -m SimpleHTTPServer 8000')
                self.webserver.expect('Serving HTTP on 0.0.0.0 port 8000', timeout=60)
            else:
                session.sendline('ping -c 3 %s'% self.webserver.ipaddr)
                session.expect(session.prompt)
                session.sendline('curl http://%s:8000'% self.webserver.ipaddr)
                self.webserver.expect(['%s\s.*GET.*200\s-'% session.dut_ipaddr])
                session.expect('DOCTYPE html PUBLIC.*/html>')
                session.expect(session.prompt)
            log_message(self, "Device: " + session.name + " curl PASS")

        self.testCleanup()
        log_message(self, 'Testing ' + self.docker_host.name + ' FINISH', True)

    def runTest(self):

        # tests both vlan and direct connections

        self.docker_host = docker_host_vlan
        self.do_test()
        self.docker_host = docker_host_direct
        self.do_test()

        log_message(self, 'Test PASS', True)

    def testCleanup(self):
        self.recover()

    def recover(self):
        # maybe cleanup the containers?
        self.webserver.sendcontrol('c')
        self.webserver.expect(self.webserver.prompt)

