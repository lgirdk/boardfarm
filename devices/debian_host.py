import os
import base
import pexpect
import time
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
    name = None
    deploy_script_name = 'deploy-boardfarm-nodes.sh'
    # default container type, this must match a class type in the devices directory
    container_type = 'debian'
    color = 'magenta'
    dyn_dev_name="lan"
    ifaces_port_space=10000

    def __init__(self, *args, **kwargs):
        """This is invoked when the json is parsed"""
        self.start_ssh_port = kwargs.pop("start_ssh_port",5000)
        self.start_web_port = kwargs.pop("start_web_port",8000)
        self.interfaces = kwargs.pop("interfaces", None)
        self.proxydir = '0'
        self.proxyip  = '0'

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

                # these 2 option are for direct connections only
                if opt.split(':')[0] == 'proxy-dir':
                    self.proxydir = opt.split(':')[1]
                if opt.split(':')[0] == 'proxy-ip':
                    self.proxyip = opt.split(':')[1]

        # logs on to the host where eventually the containers will be spawned
        super(DockerFactory, self).__init__(*args, **kwargs)

    def spawn_containers(self, count, ifaces = None):
        """
        This method is invoked by the test case
        count:          the number of containers to be created per interface
        iface_override: an override for the interface value in the json
                        can be passed as "iface" or "iface.vlan"
        """
        assert count != 0,"Number of containers must be greater than 0"
        self.count = count

        if ifaces is None:
            ifaces = self.interfaces


        # must be a list not a string, lets make it a list
        if isinstance(ifaces, basestring):
            ifaces = [ifaces]

        # this will be replaced by python multiline scripts
        dbn = os.getcwd()+"/"+self.deploy_script_name

        # copy the shell script over
        dst=os.path.join('/tmp', os.path.basename(dbn))
        #self.copy_file_to_server(dbn, dst)
        from common import copy_file_to_server
        cmd = "cat %s | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -x %s@%s \"cat - > %s; echo %s\""\
              % (dbn, self.username, self.ipaddr, dst, dst)

        copy_file_to_server(cmd, self.password, "/tmp")

        # source the file
        self.sendline('. %s' % dst)
        self.expect(self.prompt)

        # TO DO: use ephemeral port (and a way to share which port is assigned)
        # 1st iface starts at STARTSSHPORT
        # 2nd iface starts at STARTSSHPORT+self.ifaces_port_space
        # 3rd iface starts at STARTSSHPORT+(self.ifaces_port_space*2)
        # and so on (within limits), so there is no collision for the port values

        for iface_idx,iface_and_vlan in enumerate(ifaces):
            iface = iface_and_vlan.split('.')[0]
            vlan  = iface_and_vlan.split('.')[1] if '.' in iface_and_vlan else None

            vlan_str = vlan if vlan is not None else ""
            vlan_int = int(vlan) if vlan is not None else 0
            sshport  = self.start_ssh_port+(int(self.ifaces_port_space)*iface_idx)
            webport  = self.start_web_port+(int(self.ifaces_port_space)*iface_idx)

            self.sendline('export STARTSSHPORT=%s'%sshport)
            self.expect(self.prompt)
            self.sendline('export STARTWEBPORT=%s;'%webport)
            self.expect(self.prompt)
            self.sendline('export IFACE=%s'%iface)
            self.expect(self.prompt)

            # str(vlan) needs to be passed as "None" for no vlan (hence the str)
            self.sendline('create_container_lan_factory %s %s %s %s'%(str(vlan),
                                                                      str(self.count-1),
                                                                      self.proxydir,
                                                                      self.proxyip))
            # polls for the prompt
            # eventually all this will done by docker swarm
            for i in range(20*self.count):
                if 0 != self.expect([ pexpect.TIMEOUT ] + self.prompt, timeout=5):
                    break

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
            import devices
            for c in range(self.count):
                index = str(c+1) #if c != 0 else ''
                multiplier= 100  if vlan is not None else 10
                p = int(sshport) + vlan_int + (c*multiplier)

                # the name of the will be the same as it used to for vlan connections
                # but for direct connection the name will include the iface
                _name = None
                if vlan is None:
                    _name = iface + self.dyn_dev_name + index
                else:
                    _name = self.dyn_dev_name + "-" + vlan_str + "-" + index

                #cont_session = devices.create_session(self.container_type, _name, self.ipaddr, str(p), self.color)
                my_kwargs ={ 'name':_name, 'ipaddr':self.ipaddr, 'port':str(p), 'color': self.color }

                cont_session = devices.get_device(self.container_type, **my_kwargs)
                if cont_session is None:
                    raise Exception('Session '+ _name + ' is None')

                self.container_list.append(cont_session)

            self.sendline('docker ps -f name="%s-%s" '%(iface, vlan_str))
            self.expect(self.prompt)
        print "Total num of pexect sessions: %d"%len(self.container_list)

        print_bold("Containers initialised")

