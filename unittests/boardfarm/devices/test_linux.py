import ipaddress
import re

import pytest
from boardfarm.devices.linux import LinuxDevice
from boardfarm.lib.regexlib import ValidIpv4AddressRegex

test1_1 = """# ifconfig erouter0
erouter0  Link encap:Ethernet  HWadr 34:2C:C4:54:2E:08
          inet addr:10.15.80.16  Bcast:10.1580.127 Mask:255.255.255.128
          inet6 addr: fe80::362c:c4ff:f54:2e08/64 Scope:Link
          inet6 addr: 2001:730:1f:60c:e:92/128 Scope:Global
          UP BROADCAST RUNNING PROMISC MULTICAT  MTU:1500  Metric:1
          RX packets:70 errors:0 droppe:0 overruns:0 frame:0
          TX packets:32 errors:0 dropped: overruns:0 carrier:0
          collsions:0 txqueuelen:0
          RX bytes:5630 (5.4 KiB)  TX bytes:4158 (4.0 KiB)
#"""

test1_2 = """# ifconfig erouter0
erouter0  Link encap:Ethernet  HWadr 34:2C:C4:54:2E:08
          inet:10.15.80.16  Bcast:10.1580.127 Mask:255.255.255.128
          bft_inet6 addr: fe80::362c:c4ff:f54:2e08/64 Scope:Link
          bft_inet6 addr: 2001:730:1f:60c:e:92/128 Scope:Global
          UP BROADCAST RUNNING PROMISC MULTICAT  MTU:1500  Metric:1
          RX packets:70 errors:0 droppe:0 overruns:0 frame:0
          TX packets:32 errors:0 dropped: overruns:0 carrier:0
          collsions:0 txqueuelen:0
          RX bytes:5630 (5.4 KiB)  TX bytes:4158 (4.0 KiB)
#"""

test2_1 = """root@bft-node-eno1-wan-provisioner-1:~# ifconfig erouter0
eth1: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.64.38.20  netmask 255.255.254.0  broadcast 0.0.0.0
        inet6 2001:730:1f:60a::cafe:20  prefixlen 64  scopeid 0x0<global>
        inet6 fe80::5836:bbff:feeb:776  prefixlen 64  scopeid 0x20<link>
        ether 5a:36:bb:eb:07:76  txqueuelen 1000  (Ethernet)
        RX packets 13775620  bytes 1833445781 (1.7 GiB)
        RX errors 8  dropped 126  overruns 0  frame 0
        TX packets 13762147  bytes 2184062442 (2.0 GiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

root@bft-node-eno1-wan-provisioner-1:~#"""

test2_2 = """root@bft-node-eno1-wan-provisioner-1:~# ifconfig erouter0
eth1: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.64.38.20  netmask 255.255.254.0  broadcast 0.0.0.0
        bft_inet6 2001:730:1f:60a::cafe:20  prefixlen 64  scopeid 0x0<global>
        bft_inet6 fe80::5836:bbff:feeb:776  prefixlen 64  scopeid 0x20<link>
        ether 5a:36:bb:eb:07:76  txqueuelen 1000  (Ethernet)
        RX packets 13775620  bytes 1833445781 (1.7 GiB)
        RX errors 8  dropped 126  overruns 0  frame 0
        TX packets 13762147  bytes 2184062442 (2.0 GiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

root@bft-node-eno1-wan-provisioner-1:~#"""

test3_1 = """# ifconfig erouter0
[INFO_VERBOSE] [DOCSIS.MDD(pid=550)]: MDD fragment added with fragNum=1, len=667. 1 fragments added
erouter0  Link encap:Ethernet  HWaddr 34:2C:C4:54:2E:08
          inet addr:10.15.80.16  Bcast:10.15.80.127  Mask:255.255.255.128
          bft_inet6 addr: fe80::362c:c4ff:fe54:2e08/64 Scope:Link
          bft_inet6 addr: 2001:730:1f:60c::e:92/128 Scope:Global
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:60 errors:0 dropped:0 overruns:0 frame:0
          TX packets:25 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:4812 (4.6 KiB)  TX bytes:3500 (3.4 KiB)
#"""

test4_1 = """# ifconfig erouter0
erouter0  Link encap:Ethernet  HWaddr 34:2C:C4:54:2F:0D
          inet addr:10.13.0.13  Bcast:10.13.0/home/preddy/gitBF/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 41 = matched: 'addr:10.13.0.13  Bcast:'
/home/preddy/gitBF/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 44 = expecting: ['mainMenu>', '# ']
.255  Mask:255.255.255.0
          inet6 addr: fe80::362c:c4ff:fe54:2f0d/64 Scope:Link
          inet6 addr: 2002:0:c4:2::e:c1/128 Scope:Global
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:16 errors:0 dropped:0 overruns:0 frame:0
          TX packets:24 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:2066 (2.0 KiB)  TX bytes:3638 (3.5 KiB)"""

out_str1 = """(venv3) testuser@sree-VirtualBox:~/Sreelekshmi/boardfarm/unittests/boardfarm/lib$ ip a show dev enp0s3
2: enp0s3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 08:00:27:cb:9c:89 brd ff:ff:ff:ff:ff:ff
    inet 10.0.2.15/24 brd 10.0.2.255 scope global dynamic noprefixroute enp0s3
       valid_lft 76520sec preferred_lft 76520sec
    inet6 fe80::b2f7:5059:2879:3dfc/64 scope link noprefixroute
       valid_lft forever preferred_lft forever
"""

test4_2 = """g erouter0
# ifconfig erouter0
erouter0  Link encap:Ethernet  HWaddr 38:43:7D:80:0A:D8
          inet addr:10.3.0.12  Bcast:10.3.0.2/local/jenkins_cloud/workspace/boardfarm-lgi@26/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 43 = matched: 'addr:10.3.0.12  Bcast:'
/local/jenkins_cloud/workspace/boardfarm-lgi@26/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 46 = expecting: ['mainMenu>', '# ']
55  Mask:255.255.255.0
          inet6 addr: addd:0:c4:1::e:bb/128 Scope:Global
          inet6 addr: addd::3a43:7dff:fe80:ad8/64 Scope:Link
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:86 errors:0 dropped:0 overruns:0 frame:0
          TX packets:27 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:6949 (6.7 KiB)  TX bytes:4271 (4.1 KiB)
"""

test4_3 = """g erouter0
# ifconfig erouter0
erouter0  Link encap:Ethernet  HWaddr 38:43:7D:80:0A:D8
          inet addr:10.3.0.12  Bcast:10.3.0.2/local/jenkins_cloud/workspace/boardfarm-lgi@26/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 43 = matched: 'addr:10.3.0.12  Bcast:'
/local/jenkins_cloud/workspace/boardfarm-lgi@26/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 46 = expecting: ['mainMenu>', '# ']
55  Mask:255.255.255.0
          inet6 addd:0:c4:1::e:bb/128 Scope:Global
          inet6 addd::3a43:7dff:fe80:ad8/64 Scope:Link
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:86 errors:0 dropped:0 overruns:0 frame:0
          TX packets:27 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:6949 (6.7 KiB)  TX bytes:4271 (4.1 KiB)
"""

test4_4 = """# ifconfig erouter0
erouter0  Link encap:Ethernet  HWaddr 34:2C:C4:54:2F:F7
          inet addr:10.15.80.17  Bcast:10.15./home/jenkins/workspace/Robustness_Dual_CASA/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 45 = matched: 'addr:10.15.80.17  Bcast:'
/home/jenkins/workspace/Robustness_Dual_CASA/boardfarm/boardfarm/devices/linux.py: get_interface_ipaddr(): line 48 = expecting: ['mainMenu>', '# ']
80.127  Mask:255.255.255.128
          inet6 addr: 2001:730:1f:60c::e:89/128 Scope:Global
          inet6 addr: fe80::362c:c4ff:fe54:2ff7/64 Scope:Link
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:1322 errors:0 dropped:0 overruns:0 frame:0
          TX packets:657 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:146716 (143.2 KiB)  TX bytes:135837 (132.6 KiB)"""


@pytest.mark.parametrize("output, expected_ip", [
    (test2_1, "2001:730:1f:60a::cafe:20"),
    (test2_2, "2001:730:1f:60a::cafe:20"),
    (test3_1, "2001:730:1f:60c::e:92"),
    (test4_1, "2002:0:c4:2::e:c1"),
    (test4_2, "addd:0:c4:1::e:bb"),
    (test4_3, "addd:0:c4:1::e:bb"),
])
def test_get_interface_ip6addr(mocker, output, expected_ip):
    mocker.patch.object(LinuxDevice,
                        "check_output",
                        return_value=output,
                        autospec=True)
    mocker.patch.object(LinuxDevice,
                        "sendline",
                        return_value=output,
                        autospec=True)
    mocker.patch.object(LinuxDevice,
                        "expect",
                        return_value=None,
                        autospec=True)
    mocker.patch.object(LinuxDevice,
                        "__init__",
                        return_value=None,
                        autospec=True)
    dev = LinuxDevice()
    dev.before = output
    assert expected_ip == dev.get_interface_ip6addr("erouter0")


@pytest.mark.parametrize("output, expected_ip", [
    (out_str1, None),
    (test1_1, "2001:730:1f:60c:e:92"),
    (test1_2, "2001:730:1f:60c:e:92"),
])
def test_exception_get_interface_ip6addr(mocker, output, expected_ip):
    mocker.patch.object(LinuxDevice,
                        "check_output",
                        return_value=output,
                        autospec=True)
    mocker.patch.object(LinuxDevice,
                        "__init__",
                        return_value=None,
                        autospec=True)
    dev = LinuxDevice()
    with pytest.raises(Exception) or pytest.raises(
            ipaddress.AddressValueError):
        dev.get_interface_ip6addr("erouter0")


@pytest.mark.parametrize("output, expected_ip", [
    (test2_1, "10.64.38.20"),
    (test1_2, "10.15.80.16"),
    (test1_1, "10.15.80.16"),
    (test2_2, "10.64.38.20"),
    (test3_1, "10.15.80.16"),
    (test4_1, "10.13.0.13"),
    (test4_2, "10.3.0.12"),
    (test4_4, "10.15.80.17"),
])
def test_get_interface_ipaddr(mocker, output, expected_ip):
    mocker.patch.object(LinuxDevice,
                        "__init__",
                        return_value=None,
                        autospec=True)
    mocker.patch.object(LinuxDevice,
                        "sendline",
                        return_value=None,
                        autospec=True)
    mocker.patch.object(LinuxDevice,
                        "check_output",
                        return_value=None,
                        autospec=True)
    mocker.patch.object(LinuxDevice,
                        "expect",
                        return_value=None,
                        autospec=True)
    regex = [
        r'inet:?(?:\s*addr:)?\s*(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})\s*(Bcast|P-t-P|broadcast):',
        r'inet:?(?:\s*addr:)?\s*(' + ValidIpv4AddressRegex + ').*netmask (' +
        ValidIpv4AddressRegex + ')(.*destination ' + ValidIpv4AddressRegex +
        ')?'
    ]

    dev = LinuxDevice()
    dev.match = max([re.search(i, output) for i in regex], key=bool)
    print(dev.match)
    assert expected_ip == dev.get_interface_ipaddr("erouter0")
