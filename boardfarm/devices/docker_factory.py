import atexit
import codecs
import json
import os
import pkgutil
import re
import sys
from collections import defaultdict
from threading import Lock

import pexpect
from boardfarm.devices import get_device, linux
from boardfarm.exceptions import DeviceDoesNotExistError
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from boardfarm.tests_wrappers import run_with_lock

lock = Lock()


class DockerFactory(linux.LinuxDevice):
    """
    A docker host that can spawn various types of containers.

    DockerFactory is based up on master-slave concept.
    Docker factory will connect to a master/orchestrator.
    Based on the env parameters provided it will jump to child docker engine
    using SSH sockets.
    Each pexpect session resolves to one child docker engine connection.

    DockerFactory will be used for following applications:
        - To configure docker networks for North/South bound interfaces of board.
        - To build docker image ``bft:node``
        - To load a docker image to remote docker engine from mirror.
        - To create docker containers connecting to pre-configured docker networks

    Initialization will handle environement setup for docker orchestrator.
    init parameters need to be passed from boardfarm config.

    Docker factory communicates with child docker engines by exporting env

    | ``export DOCKER_HOST=ssh://<engine IP>``

    :BF json template:

    .. code-block:: json

        {
            "iface": "${lan_iface}",
            "ipaddr": "orchestrator ip address>",
            "username": "<orchestrator username>",
            "password": "<orchestrator password>",
            "env": {
                "DOCKER_HOST": "${DOCKER_ENGINE2}",
                "lan_iface": "<physical interface on factory for docker network>",
                "options": "options required to be added for containers created by this factory"
            },
            "docker_network": "<docker network name> based on board name",
            "name": "lan_factory",
            "type": "docker-factory"
       }

    DockerFactory init will take care of following activities:

    1. JSON code parsing
    2. ``pexpect`` connection to orchestrator
    3. Env configuration to respective docker engines
    4. Docker interface validation and docker network configuration
    5. If pre-configured target specified in JSON, deploy target containers

    :param ``*args``: mandatory args **model**
    :type ``*args``: tuple
    :param ``**kwargs``: mandatory kwargs **mgr, name**
    :type ``**kwargs``: dict

    .. note::

        1. ``password`` used in docker factory needs to be hex encrypted.
        2. ``iface`` used in docker factory must be a physical interface on the child docker engine.
        3. ``DockerFactory`` by default uses localhost, and local ifaces

    """

    model = "docker-factory"
    prompt = ["docker_session>"]
    created_docker = False
    created_network = True

    extra_devices = []
    target_cname = []
    del_docker_network = False
    build_image_path = None

    def __str__(self):
        return self.name

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        atexit.register(self.run_cleanup_cmd)
        self.args = args
        self.kwargs = kwargs
        self.container_id = 1
        self.dev = kwargs.pop("mgr", None)

        self.ipaddr = kwargs.pop("ipaddr", "localhost")
        self.username = kwargs.pop("username", "root")
        self.password = codecs.decode(
            kwargs.pop("password", "626967666f6f7431"), "hex").decode("ascii")
        self.docker_engine = None
        self.network_options = ""

        self.device_counter = defaultdict(int)

        # In case json provides its own env, update that to boardfarm.devices.env
        # These are meant to be exported to docker-factory not to docker-engines
        self.dev.env.update(kwargs.pop("env", {}))
        self.build_img_path = self.dev.env.pop("build_img_path", None)
        configuration = self.dev.env.pop("configure", None)

        if self.ipaddr != "localhost":
            # TOOO: we rely on correct username and key and standard port
            bft_pexpect_helper.spawn.__init__(
                self,
                command="ssh",
                args=[
                    "%s@%s" % (self.username, self.ipaddr),
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "ServerAliveInterval=60",
                    "-o",
                    "ServerAliveCountMax=5",
                ],
            )
        else:
            bft_pexpect_helper.spawn.__init__(
                self, command="bash --noprofile --norc", env=self.dev.env)

        # TODO: reused function for ssh auth for all of this
        if 0 == self.expect(["assword", pexpect.TIMEOUT], timeout=10):
            self.sendline(self.password)

        self.name = kwargs.pop("name")

        # used to create a docker network, if not present
        # docker_network creation will skip if iface is not set
        # iface needs to point to env, it should not have an explicit iface name
        self.iface = kwargs.pop("iface", None)
        assert (
            self.iface
        ), "iface needs to be provided as an arguement to docker-factory"

        self.docker_network = kwargs.pop("docker_network", None)
        if not self.docker_network:
            self.docker_network = self.name + "-" + self.dev.env["uniq_id"]
            # clean only auto-created docker-networks
            # static docker-networks will only be created if they don't exist,
            # but they will not be deleted
            self.del_docker_network = True
        else:
            # enforcing here, subnet, ip-range and gateway needs to be provided together
            # if docker_network was passed as an argument, and needs to be created
            if configuration:
                subnet = configuration.get("subnet")
                ip_range = configuration.get("ip-range")
                gateway = configuration.get("gateway")
                extra_opts = configuration.get("extra_opts", "")
                self.network_options = "--subnet %s --ip-range %s --gateway %s %s" % (
                    subnet,
                    ip_range,
                    gateway,
                    extra_opts,
                )

        if "BFT_DEBUG" in os.environ:
            self.logfile_read = sys.stdout

        self.sendline('export PS1="docker_session>"')
        self.expect(self.prompt)
        self.sendline("echo FOO")
        self.expect_exact("echo FOO")
        self.expect(self.prompt)

        if self.ipaddr != "localhost":
            print(self.dev.env)
            for k, v in self.dev.env.items():
                self.sendline("export %s=%s" % (k, v))
                self.expect(self.prompt)

        self.setwinsize(80, 200)
        self.set_cli_size(200)

        # if these interfaces are getting created let's give them time to show up
        if "DOCKER_HOST" in self.dev.env:
            out = self.check_output("echo %s" % (self.dev.env["DOCKER_HOST"]))
            if out:
                self.docker_engine = out.strip().split("//")[-1]
            else:
                raise DeviceDoesNotExistError(
                    "Factory is not configured with DOCKER_ENGINE: %s" %
                    (self.dev.env["DOCKER_HOST"]))

        prefix = "ssh %s " % self.docker_engine if self.docker_engine else ""
        for _ in range(10):
            self.sendline("%sifconfig %s" % (prefix, self.iface))
            self.expect(self.prompt)
            if ("error fetching interface information: Device not found" not in
                    self.before or prefix):
                break
            self.expect(pexpect.TIMEOUT, timeout=5)

        # enforcing here, containers will only be created using docker-network
        self.configure_docker_network()

        for target in kwargs.pop("targets", []):
            self.add_target(target)

    def add_target(self, target, docker_network=None):
        """Run a docker container from DockerFactory.

        ``add_target`` performs the following actions:
            - Validate / Build target image for container
            - Spawn the requested docker container
            - Connect the docker network to container
            - Register the target to ``boardfarm.lib.DeviceManager``

        :param docker_network: docker network to connect to target container
        :type docker_network: string
        :param target: mandatory keys **img, type, name**
        :type target: dict

        .. note::

            1. If wan containers are being spawned, ensure adding **static-routes** to ``target['options']``
            2. LAN and WAN containers both have a mgmt iface ``eth0`` and a data iface ``eth1``
            3. JSON validation for target is not handled by add_target
        """
        target_img = target["img"]
        target_type = target["type"]
        name = target["name"]

        counter = self.device_counter
        counter[name] += 1

        target_cname = target["name"] + "-${uniq_id}" + str(counter[name])

        ip = getattr(self, "docker_engine", None)
        if not ip:
            ip = self.ipaddr
        target["ipaddr"] = ip.split("@")[-1]
        target["device_mgr"] = self.dev

        options = target.get("options", [])
        if options:
            options = options.split(",")
        docker_network = self.docker_network if not docker_network else docker_network

        self.configure_docker_image(target_img)

        # TODO: check for docker image and build if needed/can
        # TODO: move default command into Dockerfile
        # TODO: list of ports to forward, http proxy port for example and ssh
        self.sendline(
            "docker run --rm --privileged --name=%s -d -p 22 %s /usr/sbin/sshd -D"
            % (target_cname, target_img))
        self.expect(self.prompt)
        self.expect(pexpect.TIMEOUT, timeout=5)
        self.created_docker = True
        self.target_cname.append(target_cname)

        self.isolate_traffic(target_cname)

        self.sendline("docker network connect %s %s" %
                      (docker_network, target_cname))
        self.expect(self.prompt)
        assert ("Error response from daemon" not in self.before
                ), "Failed to connect docker network"

        if self.network_options:
            ip = json.loads(
                self.check_output(
                    "docker inspect -f '{{json .NetworkSettings.Networks.%s}}' %s"
                    % (docker_network, target_cname)))

            assert ip["IPAddress"], (
                "Failed to set a static IPv4 Address for container : %s" %
                target_cname)

            options.append("wan-static-ip:%s/%s " %
                           (ip["IPAddress"], ip["IPPrefixLen"]))

            # IPv6 is optional
            if ip["GlobalIPv6Address"]:
                options.append(
                    "wan-static-ipv6:%s/%s" %
                    (ip["GlobalIPv6Address"], ip["GlobalIPv6PrefixLen"]))

            if ip["Gateway"]:
                options.append("static-route:0.0.0.0/0-%s" % ip["Gateway"])
        else:
            # if the IP address for interface is suppose to be assigned using DHCP
            self.sendline("docker exec %s ip address flush dev eth1" %
                          target_cname)
            self.expect(self.prompt)

        self.sendline("docker port %s | grep '22/tcp' | sed 's/.*://g'" %
                      target_cname)
        self.expect_exact("docker port %s | grep '22/tcp' | sed 's/.*://g'" %
                          target_cname)
        self.expect(self.prompt)
        target["port"] = self.before.strip()
        target["options"] = ",".join(options)
        int(self.before.strip())

        new_device = get_device(target_type, **target)
        self.extra_devices.append(new_device)

    def validate_docker_image(self, img):
        """Validate if docker image tag is already built in docker engine.

        :param img: image tag, **e.g. bft:node**
        :type img: string
        :return: ``True`` if exist, else ``False``
        :rtype: bool
        """
        out = self.check_output("docker inspect %s --format {{.Id}}" % img)
        return "Error: No such object" not in out

    @run_with_lock(lock)
    def build_docker_image(self, img="bft:node", path=None):
        """Build a docker image with tag specified by parameter img.

        Based on args passed, method will executes based on below scenarios:
            - if ``path`` is not provided, factory will build
              the local **bft:node** from Dockerfile in boardfarm/bft-node
            - if ``path`` is a URL from local mirror, factory will download
              the image. (.tar file)
            - if ``path`` is an absolute path, factory will try to load
              the image. (.tar file)
            - if ``path != None``, image is loaded using: | ``docker load -i <path> <img>``

        :param img: image tag, **e.g. bft:node**
        :type img: string
        :param path: must be absolute path to zipped docker image
        :type path: string
        """
        if path:
            if any(list(map(lambda x: x in path, ["http://", "https://"]))):
                self.sendline("curl -O %s" % path)
                self.expect_prompt(timeout=120)
                path = path.split("/")[-1]
                self.sendline("docker image load --input %s" % path)
        else:
            # try to build an image, for first time
            path = os.path.join(
                os.path.dirname(pkgutil.get_loader("boardfarm").path),
                "bft-node")
            self.sendline("docker build -t %s %s" % (img, path))
        # will give it a good 10 mins to build image.
        self.expect_prompt(timeout=600)

    def configure_docker_image(self, img="bft:node"):
        """Validate if docker image exists or build the image.

        :param img: image tag, **e.g. bft:node**
        :type img: string
        :return: ``None`` if no error, else ``raise AssertionError``
        :rtype: None
        """
        # only provide absolute path for tar image
        # else will build image from default location
        if not self.validate_docker_image(img):
            # only build an image if path is provided from config
            if self.build_img_path:
                self.build_docker_image(img, self.build_img_path)
            assert self.validate_docker_image(img), (
                "Failed to build docker image: %s" % img)

    def close(self, *args, **kwargs):
        """Close docker."""
        self.clean_docker()
        self.clean_docker_network()
        out = super(DockerFactory, self).close(*args, **kwargs)
        atexit.unregister(self.run_cleanup_cmd)
        return out

    def run_cleanup_cmd(self):
        """Run cleanup command."""
        self.clean_docker()
        self.clean_docker_network()

    def clean_docker_network(self):
        """Clean docker network."""
        self.sendcontrol("c")
        self.expect_prompt()
        if self.del_docker_network and self.created_network is True:
            self.sendline("docker network rm %s" % self.docker_network)
            self.expect(self.prompt)
            self.sendline("docker network ls")
            self.expect(self.prompt)

    def clean_docker(self):
        """Clean docker."""
        if self.created_docker:
            self.sendcontrol("c")
            self.expect_prompt()
            for c in self.target_cname:
                self.sendline("docker stop %s" % c)
                self.expect(self.prompt)
                self.created_docker = False

    def validate_docker_network(self):
        """Validate if docker network is already configured.

        If the docker network is present, validate the parent iface of
        the docker network with args passed during initialization.

        :raises AssertionError: in case of iface mismatch wiht boardfarm config.

        :return: ``True`` if exist, else ``False``
        :rtype: bool
        """
        out = self.check_output(
            "docker network inspect -f {{.Options.parent}} %s" %
            self.docker_network)
        result = "Error: No such network" not in out
        if result:
            check = out.strip() in self.check_output("echo %s" % self.iface)
            # if iface provided from JSON do not match with exisitng docker-nw's parent iface, exit
            assert (
                check
            ), "Driver Issue: iface from config does not match exisiting docker network's parent iface"
        return result

    @run_with_lock(lock)
    def add_docker_network(self):
        """Create a docker network.

        Name of the docker network is selected based on the parameter
        ``docker_network`` passed as an argument.

        Docker network will use macvlan driver, and only provides
        l2 forwarding support on parent ifaces which
        is the default configuration and is commonly used for lan containers.

        | **configure details for wan networks:**

        .. code-block:: json

            {
                "iface": "${wan_iface}",
                "ipaddr": "orchestrator ip address>",
                "username": "<orchestrator username>",
                "password": "<orchestrator password>",
                "env": {
                    "DOCKER_HOST": "${DOCKER_ENGINE2}",
                    "wan_iface": "<physical interface on factory for docker network>",
                    "options": "static-route:<>, tftpd-server",
                    "configure" {
                        "subnet" : "<mandatory>",
                        "ip-range" : "<mandatory>",
                        "gateway" : "<mandatory>",
                        "extra_opts" : "optional, e.g. IPv6 details"
                    }
                },
                "docker_network": "<docker network name> based on board name",
                "name": "wan_factory",
                "type": "docker-factory"
            }

        """

        # TODO, ensure that all docker networks don't have overlapping subnet configurations.
        # completely depending on the person who writes the config.
        cmd = (
            "docker network create -d macvlan -o parent=%s %s -o macvlan_mode=bridge %s"
            % (self.iface, self.network_options, self.docker_network))
        self.sendline(cmd)
        self.expect(self.prompt)
        assert (
            "Error response from daemon: could not find an available, non-overlapping IPv4 address pool among the defaults to assign to the network"
            not in self.before)
        if " is already using parent interface " in self.before:
            # should we exit if we find this scenario?
            print(
                "Warning!! a docker-network network with same parent exists. Switching to that docker-network"
            )
            self.docker_network = re.findall("dm-(.*) is already",
                                             self.before)[0]
            self.created_network = False

    def configure_docker_network(self):
        """Validate if docker network exists or build the image.

        :raises AssertionError: if not able to create Docker network

        :return: ``None`` if no error, else ``raise AssertionError``
        :rtype: None
        """
        # iface set, we need to create network
        if not self.validate_docker_network():
            self.add_docker_network()
            assert self.validate_docker_network(), (
                "Failed to configure docker network: %s" % self.docker_network)

    @run_with_lock(lock)
    def isolate_traffic(self, cname):
        """
        Pushes the network details of mgmt iface.
        i.e. ``eth0`` to ``mgmt`` routing table and creates the necessary
        ip lookup rules for management traffic.

        :param cname: name of the container
        :type cname: string
        """
        prefix = "ssh %s " % self.docker_engine if self.docker_engine else ""
        docker_gw_ip = self.check_output(
            r"%sip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'"
            % prefix)
        docker_dev_ip = self.check_output(
            r"docker exec %s ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'"
            % cname)
        docker_nw = self.check_output(
            '%sip route | grep "dev docker0" | grep src | '
            "awk '{print $1}' | head -n1" % prefix)

        self.check_output(
            "docker exec %s bash -c 'echo \"1 mgmt\" >> /etc/iproute2/rt_tables'"
            % cname)
        self.check_output(
            "docker exec %s ip route add default via %s table mgmt" %
            (cname, docker_gw_ip))
        self.check_output("docker exec %s ip rule add from %s table mgmt" %
                          (cname, docker_dev_ip))
        self.check_output("docker exec %s ip rule add to %s table mgmt" %
                          (cname, docker_dev_ip))
        self.check_output("docker exec %s ip rule add from %s table mgmt" %
                          (cname, docker_nw))
        self.check_output("docker exec %s ip rule add to %s table mgmt" %
                          (cname, docker_nw))

        self.check_output("docker cp %s:root/.bashrc bashrc_%s" %
                          (cname, cname))
        self.check_output('echo "alias mgmt='
                          "'BIND_ADDR=%s LD_PRELOAD=/usr/lib/bind.so '"
                          '" >> bashrc_%s' % (docker_dev_ip, cname))
        self.check_output("docker cp bashrc_%s %s:root/.bashrc; rm bashrc_%s" %
                          (cname, cname, cname))
