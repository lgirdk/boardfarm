#import ipaddress
import os
import base
import pexpect
#from lib.regexlib import ValidIpv4AddressRegex

from devices import DebianBox

class DebianDockerFactory(DebianBox):
    '''
    Linux docker contaniers factory
    '''

    model = ('debian_docker_factory')
    connection_type = None
    interfaces = None
    count = 0
    vlan = None
    deploy_script_name = 'deploy-boardfarm-nodes.sh'

    def __init__(self, *args, **kwargs):

        self.count = kwargs.pop("count",2)
        self.start_port = kwargs.pop("start_port",5000)
        self.interfaces = kwargs.pop("interfaces", None)
        self.vlan = kwargs.pop("vlan")

        # not yet used
        if 'options' in kwargs:
            options = [x.strip() for x in kwargs['options'].split(',')]
            for opt in options:
                if opt.split(':')[0] == 'deploy-scritp':
                    self.deploy_script =  opt.split(':')[1]
        #logs on to the host
        return super(DebianDockerFactory, self).__init__(*args, **kwargs)

    def spanw_containers(self):
        dbn = os.getcwd()+"/"+self.deploy_script_name

        # copy the shell script over
        dst=os.path.join('/tmp', os.path.basename(dbn))
        self.copy_file_to_server(dbn, dst)

        # source the file
        self.sendline('chmod +x %s; . %s' % (dst, dst))
        self.expect(self.prompt)

        for iface in self.interfaces:
            self.sendline('set -x ; export IFACE=%s; create_container_lan_factory %s %s ;set +x' % (iface, self.vlan, str(self.count-1)))
            self.expect(self.prompt, timeout=(30*self.count))
        # validate, somehow, that we have as many containers as expected
        for iface in self.interfaces:
            self.sendline('docker ps -f name="%s-%s" | grep -v "CONTAINER ID" | wc -l' %(iface, self.vlan))
            self.expect(str(self.count))

        self.expect(self.prompt)
        self.sendline('docker ps -f name="%s-%s" '%(iface, self.vlan))
        self.expect(self.prompt)

