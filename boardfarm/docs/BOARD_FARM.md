Board Farm
==========

A "Board Farm" is simply one or more boards (such as routers) connected to a network so that they are remotely accessable to testers or developers.

There are many benefits to building a board farm, including:

* Users can simply ssh/telnet over the network to use boards and devices connected to those boards.
* It frees users from having to physically connect wires or setup their own non-standard setup at their desk or elsewhere.
* Automated build systems can run tests on boards when a new build is compiled.

This document describes how to physically setup a Board Farm.


Examples
--------

### Minimal Physical Example

![Image of Router, Network-controlled power switch, and computers](https://raw.githubusercontent.com/qca/boardfarm/master/docs/Simple_Board_Farm.jpg "Minimal Test Station")

This is one router test station. The black cylinder in the center is 1 router. The web-controlled power switch in the upper-left allows devices to be remotely power-cycled. White Ethernet cables connect devices to the local network. Three, small computers run Debian Linux. One computer is connected to the router's LAN, one computer is connected to the router's WAN, and the last computer is connected to the Serial Console of the router.

#### Ingredients

The smallest board farm requires:

* 1 board (e.g. a router).
* 1 console server. (or local serial connection (see below)
* 1 network-controlled power switch.
* 2 computers each with 2 network interfaces - Preferably Debian Linux. Can be small Raspberry PI computers, or more powerful computers (to acheive gigabit throughput).
* Several ethernet cables, and serial connector for the board.

A console server allows users to ssh/telnet to it and gain console access to boards.  They can be made for free using any Linux computer by using libraries such as [ser2net]([http://sourceforge.net/projects/ser2net/).  Console servers can also be purchased: there are open-source, linux-based console servers available from [OpenGear](http://opengear.com/products/cm4100-console-server).

Network-controlled power switches allow users to turn on and off power outlets over the network.  They can be purchased from various places with different amounts of features typically for a few hundred USD/EUR.

#### Physical Connections

Here we assume the "board" you wish to test is a router.

Ethernet connections:

    Local Network <---> eth0-Computer-eth1 <---> LAN-Router-WAN <---> eth1-Computer-eth0 <---> Local Network

Serial Connections:

    Console server <---> Router

Power Connections: Only the router needs to be plugged into the Network-controlled power switch.  All others can be connected to standard power outlets.

### Minimal Virtualised Example

#### Ingredients

Virtualised board farm requires:

* 1 board (e.g. a router)
* 1 test server
* 1 network-controlled power switch or some other means how to trigger reboot remotelly
* 1 VLAN capable switch with at least 4 ports (e.g. another router)
* Several Ethernet cables, and serial connector for the board.

A test server allows users to ssh to it and gain console access to
boards and it also runs virtualised testing machines.

Network-controlled power switches allow users to turn on and off power outlets
over the network.  They can be purchased from various places with different
amounts of features typically for a few hundred USD/EUR.

For VLAN capable switch, most of OpenWRT routers can be used.

#### Network Connections

Here we assume the "board" you wish to test is a router.

Ethernet connections are easy - everybody is connected via Ethernet port to
your VLAN capable switch. You put in Internet connection cable, yous test server
and one cable from WAN interface of the router and one from LAN interface.
Before putting everything together we need to preconfigure this switch. One
example configuration is as follows:

* Port 1 of switch - Internet cable - Untagged Vlan 99
* Port 2 of switch - Test Server - Tagged Vlan 99, 10, 11
* Port 3 of switch - Router WAN - Untagged Vlan 10
* Port 4 of switch - Router LAN - Untagged Vlan 11

It is also a good idea to configure router to be manageable from the outside -
Port 1.

Now we have plenty of connections bundled in one VLAN trunk that goes to our
Test Server where we need to decouple them. We create separate VLAN endpoints
for each one of the VLANs in the the OS running there and for VLAN99 we create a
configuration (either static or DHCP) so we can connect to the server from the
outside. For VLAN10 and VLAN 11 we create bridges to put VLAN interfaces into
and we can let them unconfigured.

Here is example configuration for openSUSE, this will differ based on your
favorite distribution

`/etc/sysconfig/network/ifcfg-inet`:
```bash
BOOTPROTO='dhcp'
ETHERDEVICE='eth0'
DHCLIENT_SET_DEFAULT_ROUTE='yes'
STARTMODE='auto'
VLAN_ID='99'
```

`/etc/sysconfig/network/ifcfg-lan-vlan`:
```bash
BOOTPROTO='none'
ETHERDEVICE='eth0'
STARTMODE='auto'
VLAN_ID='11'
```

`/etc/sysconfig/network/ifcfg-wan-vlan`:
```bash
BOOTPROTO='none'
ETHERDEVICE='eth0'
STARTMODE='auto'
VLAN_ID='10'
```

`/etc/sysconfig/network/ifcfg-lan-br`:
```bash
BOOTPROTO='none'
BRIDGE='yes'
BRIDGE_FORWARDDELAY='0'
BRIDGE_PORTS='lan-vlan'
BRIDGE_STP='off'
STARTMODE='auto'
```

`/etc/sysconfig/network/ifcfg-wan-br`:
```bash
BOOTPROTO='none'
BRIDGE='yes'
BRIDGE_FORWARDDELAY='0'
BRIDGE_PORTS='wan-vlan'
BRIDGE_STP='off'
STARTMODE='auto'
```

#### Virtual servers

For LAN and WAN computers mentioned in physical setup we can now use virtual
ones, for example using LXC. Really easy and user-friendly way to do that is to
use libvirt installed on your test server and virt-manager to control it. You
can then create two LXC hosts and unpack debian images inside, just make sure
that both of them have two virtual network cards. First one connected to
managing network between test server and them - just make sure to use static
configuration for LAN and WAN computers and that LAN computer doesn't have
default route set to test server (WAN computer on the other hand might need
this). The second network interface in case of LAN computer should be put to
lan-br and WAN one into wan-br.

#### Test server

Now all you need to do is install uucp package on your test server, create a
user account with sufficient privileges to use uc (in openSUSE member of uucp
and dialout groups), ideally add static entries for LAN and WAN conputer to
your hosts file and copy out keys and you can start running tests. You need
just unprivileged user on the test server and you can make backup of your
containers just in case some tests break them.


Setup of the Computers
----------------------

The computers connected to the boards need a few libraries:

    apt-get install -y openssh-server openssh-client sudo tftp-hpa tftpd-hpa curl socat tinyproxy iperf

Both computers need 2 network interfaces:

* `eth0` connected to the local area network
* `eth1` connected to the board

The routing table on the computers needs to be setup such that traffic to the local area network goes to eth0, while all other traffic goes through eth1, through the router.

The routing table on the LAN-side computer:

    # route -n
    Kernel IP routing table
    Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
    0.0.0.0         192.168.1.1     0.0.0.0         UG    0      0        0 eth1
    10.0.0.0        0.0.0.0         255.0.0.0       U     0      0        0 eth0
    192.168.1.0     0.0.0.0         255.255.255.0   U     0      0        0 eth1

The routing table on the WAN-side computer:

    # route -n
    Kernel IP routing table
    Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
    0.0.0.0         10.0.0.1        0.0.0.0         UG    0      0        0 eth0
    10.0.0.0        0.0.0.0         255.0.0.0       U     0      0        0 eth0
    192.168.0.0     0.0.0.0         255.255.255.0   U     0      0        0 eth1

After setting up the computers one should be able to ssh to the computers and run, for example, `iperf` throughput test through the router.

Board Farm Config File
----------------------
All routers in a board farm need an entry in the boardfarm_config.json file like so:

```json
  {
    "<name>": {
      "board_type": "<model>",
      "conn_cmd": "telnet <server> <port>",
      "devices": [
                {
                        "type": "debian",
                        "name": "wan",
                        "ipaddr": "port2",
                        "color": "cyan"
                },
                {
                        "type": "debian",
                        "name": "lan",
                        "ipaddr": "port3",
                        "color": "blue"
                }
      "powerip": "<powerserver>",
      "powerport": "<outlet>"
    }
  }
```

Where:
* `name` is any unique name at all
* `model` is a descriptive model name
* `conn_cmd` is the command to run to connect to the board
* `devices' is an array of devices that will be added, must have a WAN device at minimum
* `powerip` and `powerport` are the network-control power unit and outlet to reset the board

Using a local serial port (i.e. no console server)
----------------------
Boardfarm also supports using a local serial port. This is useful when you have
your PC connected directly to the device under test. To do so, you'd modify your
board farm JSON config file as follows:

* add `"connection_type": "local_serial"` to your board entry
* replace the current `conn_cmd` element with with `"conn_cmd": "cu -l <port> -s <speed>"` in your board entry

Where:
* `port` is the path to your serial port. One example would be `/dev/ttyUSB0`.
* `speed` is the baud rate for the serial port connection. One example would be `115200`.

Additionally, you must install the `cu` program on your connecting computer. If running,
a Debian based system, you would run:
```
apt-get install cu
```
If running openSUSE, you would run:
```
zypper in uucp
```

Starting with an Unknown board
----------------------

In a perfect world, the device you are using is already supported but that's
not always the case. This section will highlight some examples for running on
a new unsupported board.

We've added a board called 'new_device' to the boardfarm example configuration,
with this configuration you can get started easily. This example also makes use of
docker containers for the LAN and WAN virtual devices - so it's also an example of
how that works

You need to add the user to the docker group as well so the boardfarm scripts can
run docker commands. Also for the time being you need to have password-less sudo
so we can run certain networking related commands

The default configuration also assumes that you have no device to power cycle the,
so you need to watch for messages:

```
User power-cycle the device now!
```

And that would be when you manually go and power cycle the board. After that if
everything works properly, the device will come up and it will run an example test.
Since you are using an unknown board type, you will possibly see some messages
where the tool is probing network interfaces but you can ignore those for the
most part

To get started run you need to update the boardfarm config with the actual ethernet
devices you have connected to the WAN and LAN ports of the device under test. In the
example it uses enxc05627904e8 and enx0050b61bfde4 - these devices can be any device
as long as the packets arrive at the device on the right ports (e.g. you can use VLAN
devices here as well). Also, you need to update the conn_cmd attribute to be a command
that connects to the serial console of your device. This can be telnet, cu, etc as
long as it's a normal console.

After that is done you can start a basic shell that just connects to all your devices:

```
$ ./bft -n new_device -x connect
[ .. snip .. ]
==================== Begin Interact ====================
Press Ctrl-] to stop interaction and return to menu
```

If you got here, a lot went right. The scripts spawned the docker containers and
connected to the console. Go ahead and enter the menu by following the instructions:

```
Current station
  Board console: cu -l /dev/ttyUSB1 -s 115200
  wan device:    ssh root@29ea56ffcf76
  lan device:    ssh root@64386c00d161
Pro-tip: Increase kernel message verbosity with
    echo "7 7 7 7" > /proc/sys/kernel/printk
Menu
  1: Enter console
  2: List all tests
  3: Run test
  4: Reset board
  5: Enter interactive python shell
  Type a device name to connect: [u'wan', u'lan']
  x: Exit
Please select:
```

From here you can type lan, and press enter.. or wan and press enter. This will
change the shell from the device under test to the WAN and LAN docker containers.
You should verfiy that the eth0 and eth1 devices are present in each containter.
eth1 is the interface name of the device you specified in the boardfarm config.
If something went wrong you will need each command one-by-one outside of the
boardfarm scripts and see if there are errors present.

Assuming no errors, you can exit the menu and try to run another test but this
time we will let the boardfarm scripts do more than connect, they will bring up
the WAN and LAN containers where the WAN container is hosting DHCP and routing
traffic (like an ISP would) and the LAN container is grabbing an IP via DHCP from
the device under test. Also, after that basic configuration is done, it will then
run a simple test (note: you can run tests from the Interact menu as well).

```
$ ./bft -n new_device -e iPerf3Test
[ .. snip .. ]
Test suite "flash" has been specified, will attempt to run tests:
  1 RootFSBootTest from /home/mattsm/git/boardfarm/tests/rootfs_boot.pyc
Extra tests specified on command line:
  <class 'tests.iperf3_test.iPerf3Test'>
  <class 'tests.interact.Interact'>

[ .. snip .. ]
==================== Begin RootFSBootTest ====================
[ .. snip .. ]
==================== End RootFSBootTest ======================

==================== Begin iPerf3Test ====================
[ .. snip .. ]
==================== End iPerf3Test ======================

==================== Begin Interact ====================
```

The above output is severely truncated to save space, but in each section see
the output from the device under test, WAN, and LAN containers. During the run,
you should see the output from the iperf3 command showing the results of the
test, something like this:

```
[SUM]   0.00-60.05  sec   498 MBytes  69.6 Mbits/sec  322             sender
[SUM]   0.00-60.05  sec   498 MBytes  69.5 Mbits/sec                  receiver
```

NOTE: since we are running new containers each time keep in mind that the WAN
and LAN devices will be completely reset each time you start the scripts. You
could actual modify the startup and make the containers persistant across
invocations of the script. Each way has it's pros and cons

Next step is to add proper support for your new board so you can take advantage of
automated flashing and remote power and reset to completly automate your CI flow
