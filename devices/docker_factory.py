import pexpect
import sys
import os

import linux

class DockerFactory(linux.LinuxDevice):
    '''
    A docker host that can spawn various types of images
    '''

    model = ('docker-factory')
    prompt = ['docker_session>']
    created_docker_network = False
    created_docker = False
    extra_devices = []

    def __str__(self):
        return self.name

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        self.ipaddr = kwargs.pop('ipaddr', None)
        self.iface = kwargs.pop('iface', None)
        self.docker_network = kwargs.pop('docker_network', None)
        self.env = kwargs.pop('env', None)
        self.cname = kwargs.get('target_name') + '-${uniq_id}'
        self.name = kwargs.pop('name')

        if self.ipaddr is not None:
            # TOOO: we rely on correct username and key and standard port
            pexpect.spawn.__init(self, command="ssh",
                                       args=['%s' % (self.ipaddr),
                                             '-o', 'StrictHostKeyChecking=no',
                                             '-o', 'UserKnownHostsFile=/dev/null',
                                             '-o', 'ServerAliveInterval=60',
                                             '-o', 'ServerAliveCountMax=5'])
            kwargs['target_ipaddr'] = self.ipaddr
        else:
            pexpect.spawn.__init__(self, command='bash', env=self.env)
            kwargs['target_ipaddr'] = 'localhost'

        if 'BFT_DEBUG' in os.environ:
            self.logfile_read = sys.stdout
        self.expect(pexpect.TIMEOUT, timeout=1)
        self.sendline('export PS1="docker_session>"')
        self.expect(self.prompt)
        self.expect(self.prompt)
        self.set_cli_size(200)

        # iface set, we need to create network
        if self.iface is not None:
            self.sendline('docker network create -d macvlan -o parent=%s -o macvlan_mode=bridge %s' % (self.iface, self.cname))
            self.expect(self.prompt)
            self.sendline('docker network ls')
            self.expect(self.prompt)
            self.created_docker_network = True

        # TODO: check for docker image and build if needed/can
        # TODO: move default command into Dockerfile
        self.target_img = kwargs.pop('target_img')
        # TODO: list of ports to forward, http proxy port for example
        self.sendline('docker run --rm --privileged --name=%s -d -p 22 %s /usr/sbin/sshd -D' % (self.cname, self.target_img))
        self.expect(self.prompt)
        self.expect(pexpect.TIMEOUT, timeout=1)
        self.sendline('docker network connect %s %s' % (self.cname, self.cname))
        self.expect(self.prompt)
        if self.created_docker_network == True:
            self.sendline('docker exec %s ip address flush dev eth1' % self.cname)
            self.expect(self.prompt)
        self.sendline("docker port %s | grep '22/tcp' | sed 's/.*://g'" % self.cname)
        self.expect_exact("docker port %s | grep '22/tcp' | sed 's/.*://g'" % self.cname)
        self.expect(self.prompt)
        kwargs['target_port'] = self.before.strip()
        int(self.before.strip())
        self.created_docker = True

        self.target_type = kwargs['target_type']

        new_kwargs = {}
        for k, v in kwargs.iteritems():
            if k.startswith('target_'):
                new_kwargs[k.replace('target_', '')] = v

        from devices import get_device
        new_device = get_device(self.target_type, **new_kwargs)
        self.extra_devices.append(new_device)


    def close(self, *args, **kwargs):
        self.clean_docker()
        self.clean_docker_network()
        return super(DockerFactory, self).close(*args, **kwargs)

    def clean_docker_network(self):
        if self.created_docker_network == True:
            self.sendline('docker network rm %s' % self.cname)
            self.expect(self.prompt)
            self.sendline('docker network ls')
            self.expect(self.prompt)

    def clean_docker(self):
        if self.created_docker == True:
            self.sendline('docker stop %s' % self.cname)
            self.expect(self.prompt)
            self.sendline('docker rm %s'% self.cname)
            self.expect(self.prompt)
