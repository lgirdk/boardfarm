#import ipaddress
import os
import base
import pexpect
import time
from lib.regexlib import ValidIpv4AddressRegex
from devices import DebianBox
from library import print_bold

class DockerFactory(DebianBox):
    '''
    Linux docker contaniers factory
    The connection type is determined by the interface key,value pair:

    direct connection: "interfaces": [ "enx503eaa8b4fec", "enx503eaa8b7ae4" ]
    vlan   connection: "interfaces": [ "enp1s0.104" ]

    at the moment no more than 2 interfaces are supported (containers port collision)
    '''

    model = ('docker_factory')
    interfaces = None
    count = 0
    deploy_script_name = 'deploy-boardfarm-nodes.sh'
    # default container type, this must match a class type in the devices directory
    container_type = 'DebianBox'
    color = 'magenta'
    dyn_dev_name="lan"
    ifaces_port_space=10000

    def __init__(self, *args, **kwargs):
        """This is invoked when the json is parsed"""
        self.start_ssh_port = kwargs.pop("start_ssh_port",5000)
        self.start_web_port = kwargs.pop("start_web_port",8000)
        self.interfaces = kwargs.pop("interfaces", None)

        self.container_list = []

        # not yet used
        if 'options' in kwargs:
            options = [x.strip() for x in kwargs['options'].split(',')]
            for opt in options:
                if opt.split(':')[0] == 'deploy-script':
                    self.deploy_script =  opt.split(':')[1]
                if opt.split(':')[0] == 'dyn-dev-name':
                    self.dyn_dev_name = opt.split(':')[1]
                if opt.split(':')[0] == 'ifaces-port-offset':
                    self.ifaces_port_space = opt.split(':')[1]
                if opt.split(':')[0] == 'container-type':
                    self.container_type = opt.split(':')[1]


        # logs on to the host where eventually the containers will be spawned
        super(DockerFactory, self).__init__(*args, **kwargs)

    def spawn_containers(self, count):
        """This method is invoked by the test case"""
        assert count != 0,"Number of containers must be greater than 0"
        self.count = count

        # this will be replaced by python multiline scripts
        dbn = os.getcwd()+"/"+self.deploy_script_name

        # copy the shell script over
        dst=os.path.join('/tmp', os.path.basename(dbn))
        self.copy_file_to_server(dbn, dst)

        # source the file
        self.sendline('chmod +x %s; . %s' % (dst, dst))
        self.expect(self.prompt)

        # 1st iface starts at STARTSSHPORT
        # 2nd iface starts at STARTSSHPORT+self.ifaces_port_space
        # 3rd iface starts at STARTSSHPORT+(self.ifaces_port_space*2)
        # and so on (within limits), so there is no collision for the port values

        for iface_idx,iface_and_vlan in enumerate(self.interfaces):
            iface = iface_and_vlan.split('.')[0]
            vlan  = iface_and_vlan.split('.')[1] if '.' in iface_and_vlan else None

            vlan_str = vlan if vlan is not None else ""
            vlan_int = int(vlan) if vlan is not None else 0
            sshport  = self.start_ssh_port+(int(self.ifaces_port_space)*iface_idx)
            webport  = self.start_web_port+(int(self.ifaces_port_space)*iface_idx)
            self.sendline('export STARTSSHPORT=%s; export STARTWEBPORT=%s; export IFACE=%s; create_container_lan_factory %s %s'%(sshport,
                                                                                                                                 webport,
                                                                                                                                 iface,
                                                                                                                                 str(vlan), # this needs to be passed as "None" for no vlan
                                                                                                                                 str(self.count-1)))
            # it woudl be nice to have something to poll,
            # eventually all this will done by docker swarm
            self.expect(self.prompt, timeout=(30*self.count))

            # validate, that we have as many containers as expected
            cmd = '[ `docker ps -f name=' + iface + '-' + vlan_str + ' | grep -v "CONTAINER ID" | wc -l ` -eq ' + str(self.count) + ' ] && echo True'
            for i in range(100):
                self.sendline(cmd)
                self.expect_exact(['echo True'])
                expect_idx = self.expect(['True', pexpect.TIMEOUT], timeout=3)
                self.expect(self.prompt)
                if expect_idx == 0:
                    break
                else:
                    # this could take sometime on a large number of containers
                    time.sleep(5)

            # at the moment the dhclient is run in the bash function
            # but eventually it will be in a function of its own
            for c in range(self.count):
                index = str(c+1) if c != 0 else ''
                multiplier= 100  if vlan is not None else 10
                p = int(self.start_ssh_port) + vlan_int + (c*multiplier)
                _name = iface + self.dyn_dev_name + index
                try:
                    klass = globals()[self.container_type]

                    print("name=" + _name + ", ipaddr=" + self.ipaddr + ", port=" + str(p) + ", color=" + self.color)

                    cont_session = klass('name', 'ipaddr', 'port', name   = _name,
                                                                   ipaddr = self.ipaddr,
                                                                   port   = str(p),
                                                                   color  = self.color)
                    self.container_list.append(cont_session)
                except:
                    # should this always fail? or should it be decided by the caller?
                    raise Exception('Failed to instantiate '+ _name)

            self.sendline('docker ps -f name="%s-%s" '%(iface, vlan_str))
            self.expect(self.prompt)
        print "Total num of pexect sessions: %d"%len(self.container_list)

        # checks that every container has an IP address (dhclinet is done in the bash function at the moment)
        # to be revisited
        names = []
        for session in self.container_list:
            for j in range(10):
                session.sendline('ip a show dev eth1')
                i = session.expect([ValidIpv4AddressRegex, pexpect.TIMEOUT], timeout=3)
                if i == 0:
                    break
                else:
                    session.expect(session.prompt)
                    time.sleep(3)

            if j >= 10:
                raise Exception( session.name+': failed to get an ip address')
            else:
                print '%s IP: %s' %(session.name, session.after)
                names.append(session.name)
            session.expect(session.prompt)
        print_bold("Containers %r initialised"% names)

