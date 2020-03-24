import atexit
import os
import re
import sys

import pexpect
from boardfarm.devices import env, get_device
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper

from . import linux


class DockerFactory(linux.LinuxDevice):
    '''
    A docker host that can spawn various types of images
    '''

    model = ('docker-factory')
    prompt = ['docker_session>']
    created_docker_network = False
    created_docker = False
    extra_devices = []
    target_cname = []
    created_network = True

    def __str__(self):
        return self.name

    def __init__(self, *args, **kwargs):
        atexit.register(self.run_cleanup_cmd)
        self.args = args
        self.kwargs = kwargs

        self.ipaddr = kwargs.pop('ipaddr', None)
        self.username = kwargs.pop('username', 'root')
        self.password = kwargs.pop('password', 'bigfoot1')

        self.dev = kwargs.pop('mgr', None)

        if self.ipaddr is not None:
            # TOOO: we rely on correct username and key and standard port
            bft_pexpect_helper.spawn.__init__(
                self,
                command="ssh",
                args=[
                    '%s@%s' % (self.username, self.ipaddr), '-o',
                    'StrictHostKeyChecking=no', '-o',
                    'UserKnownHostsFile=/dev/null', '-o',
                    'ServerAliveInterval=60', '-o', 'ServerAliveCountMax=5'
                ])
        else:
            bft_pexpect_helper.spawn.__init__(
                self, command='bash --noprofile --norc', env=env)
            self.ipaddr = 'localhost'

        self.iface = kwargs.pop('iface', None)
        self.docker_network = kwargs.pop('docker_network', None)
        self.name = kwargs.pop('name')
        self.cname = self.name + "-" + env["uniq_id"]

        if 'BFT_DEBUG' in os.environ:
            self.logfile_read = sys.stdout

        # TODO: reused function for ssh auth for all of this
        if 0 == self.expect(['assword', pexpect.TIMEOUT], timeout=10):
            self.sendline(self.password)

        self.sendline('export PS1="docker_session>"')
        self.expect(self.prompt)
        self.sendline('echo FOO')
        self.expect_exact('echo FOO')
        self.expect(self.prompt)

        if self.ipaddr != 'localhost':
            print(env)
            for k, v in env.items():
                self.sendline('export %s=%s' % (k, v))
                self.expect(self.prompt)

        self.set_cli_size(200)

        # if these interfaces are getting created let's give them time to show up
        for i in range(10):
            self.sendline('ifconfig %s' % self.iface)
            self.expect(self.prompt)
            if 'error fetching interface information: Device not found' not in self.before:
                break
            self.expect(pexpect.TIMEOUT, timeout=5)

        # iface set, we need to create network
        if self.iface is not None:
            self.sendline(
                'docker network create -d macvlan -o parent=%s -o macvlan_mode=bridge %s'
                % (self.iface, self.cname))
            self.expect(self.prompt)
            assert 'Error response from daemon: could not find an available, non-overlapping IPv4 address pool among the defaults to assign to the network' not in self.before
            if ' is already using parent interface ' in self.before:
                self.cname = re.findall('dm-(.*) is already', self.before)[0]
                self.created_network = False
            self.sendline('docker network ls')
            self.expect_exact('docker network ls')
            self.expect(self.prompt)
            assert self.cname in self.before, "dynamically created docker network not found in list. network id - %s " % self.cname
            self.created_docker_network = True

        for target in kwargs.pop('targets'):
            self.add_docker_node(target)

    def add_docker_node(self, target, docker_network=None):
        target_img = target['img']
        target_type = target['type']
        target_cname = target['name'] + '-${uniq_id}'
        docker_network = self.cname if docker_network is None else docker_network

        # TODO: check for docker image and build if needed/can
        # TODO: move default command into Dockerfile
        # TODO: list of ports to forward, http proxy port for example and ssh
        self.sendline(
            'docker run --rm --privileged --name=%s -d -p 22 %s /usr/sbin/sshd -D'
            % (target_cname, target_img))
        self.expect(self.prompt)
        assert "Unable to find image" not in self.before, "Unable to find %s image!" % target_img
        self.expect(pexpect.TIMEOUT, timeout=1)
        self.sendline('docker network connect %s %s' %
                      (docker_network, target_cname))
        self.expect(self.prompt)
        assert 'Error response from daemon' not in self.before, "Failed to connect docker network"
        if self.created_docker_network == True:
            self.sendline('docker exec %s ip address flush dev eth1' %
                          target_cname)
            self.expect(self.prompt)
        self.sendline("docker port %s | grep '22/tcp' | sed 's/.*://g'" %
                      target_cname)
        self.expect_exact("docker port %s | grep '22/tcp' | sed 's/.*://g'" %
                          target_cname)
        self.expect(self.prompt)
        target['port'] = self.before.strip()
        int(self.before.strip())
        self.created_docker = True

        target['ipaddr'] = self.ipaddr
        target['device_mgr'] = self.dev
        new_device = get_device(target_type, **target)
        self.extra_devices.append(new_device)

        self.target_cname.append(target_cname)

    def close(self, *args, **kwargs):
        self.clean_docker()
        self.clean_docker_network()
        return super(DockerFactory, self).close(*args, **kwargs)

    def run_cleanup_cmd(self):
        self.clean_docker()
        self.clean_docker_network()

    def clean_docker_network(self):
        if self.created_docker_network == True and self.created_network == True:
            self.sendline('docker network rm %s' % self.cname)
            self.expect(self.prompt)
            self.sendline('docker network ls')
            self.expect(self.prompt)
            self.created_docker_network = False

    def clean_docker(self):
        if self.created_docker == True:
            for c in self.target_cname:
                self.sendline('docker stop %s' % c)
                self.expect(self.prompt)
                self.sendline('docker rm %s' % c)
                self.expect(self.prompt)
                self.created_docker = False
