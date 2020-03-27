import ipaddress

import pytest
from boardfarm.exceptions import BftIfaceNoIpV4Addr, BftIfaceNoIpV6Addr
from boardfarm.lib.bft_interface import bft_iface


class Dummy:
    def check_output(self, cmd):
        pass

    pass


out_str1 = '''(venv3) testuser@sree-VirtualBox:~/Sreelekshmi/boardfarm/unittests/boardfarm/lib$ ip a show dev enp0s3
2: enp0s3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 08:00:27:cb:9c:89 brd ff:ff:ff:ff:ff:ff
    inet 10.0.2.15/24 brd 10.0.2.255 scope global dynamic noprefixroute enp0s3
       valid_lft 76520sec preferred_lft 76520sec
    inet6 fe80::b2f7:5059:2879:3dfc/64 scope link noprefixroute
       valid_lft forever preferred_lft forever
'''

out_str2 = '''root@bft-node-data-106-0:~# ip a
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host
       valid_lft forever preferred_lft forever
'''

out_str3 = '''
204: eth0@if205: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default
    link/ether 02:42:c0:a8:32:04 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    inet 192.168.50.4/24 brd 192.168.50.255 scope global eth0
       valid_lft forever preferred_lft forever
'''

out_str4 = '''
475: eth1@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    link/ether 3e:73:cb:6b:49:ba brd ff:ff:ff:ff:ff:ff link-netnsid 0
    inet 10.64.38.106/23 scope global eth1
       valid_lft forever preferred_lft forever
    inet6 2001:730:1f:60a::cafe:106/64 scope global
       valid_lft forever preferred_lft forever
    inet6 fe80::3c73:cbff:fe6b:49ba/64 scope link
       valid_lft forever preferred_lft forever
'''

out_str5 = '''
erouter0  Link encap:Ethernet  HWaddr 68:02:B8:02:C5:04
          inet addr:10.3.0.23  Bcast:10.3.0.255  Mask:255.255.255.0
          bft_inet6 addr: 2002:0:c4:1::e:c0/128 Scope:Global
          bft_inet6 addr: fe80::6a02:b8ff:fe02:c504/64 Scope:Link
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:6208 errors:0 dropped:0 overruns:0 frame:0
          TX packets:81 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:432494 (422.3 KiB)  TX bytes:10636 (10.3 KiB)
'''

out_str6 = '''
erouter0  Link encap:Ethernet  HWaddr 68:02:B8:02:C5:04
          bft_inet6 2002:0:c4:1::e:c0/128 Scope:Global
          bft_inet6 fe80::6a02 Scope:Link
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:6208 errors:0 dropped:0 overruns:0 frame:0
          TX packets:81 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:432494 (422.3 KiB)  TX bytes:10636 (10.3 KiB)
'''

out_str7 = '''
erouter0  Link encap:Ethernet  HWaddr 68:02:B8:02:C5:04
s         inet addr:10.3.0.21 Bcast:10.3.0.255  Mask:255.255.255.0
          bft_inet6 fe80:6a02 Scope:Link
          UP BROADCAST RUNNING PROMISC MULTICAST  MTU:1500  Metric:1
          RX packets:6208 errors:0 dropped:0 overruns:0 frame:0
          TX packets:81 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:432494 (422.3 KiB)  TX bytes:10636 (10.3 KiB)
'''


@pytest.mark.parametrize("command_output,expected",
                         [(out_str5, "2002:0:c4:1::e:c0"), (out_str2, "::1")])
def test_get_ipv6(mocker, command_output, expected):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=command_output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    obj.get_interface_ipv6addr(command_output)
    assert obj.ipv6 == ipaddress.IPv6Interface(expected).ip


@pytest.mark.parametrize("command_output,expected",
                         [(out_str4, "fe80::3c73:cbff:fe6b:49ba"),
                          (out_str5, "fe80::6a02:b8ff:fe02:c504")])
def test_get_ip_link_local_ipv6(mocker, command_output, expected):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=command_output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    obj.get_interface_ipv6addr(command_output)
    assert obj.ipv6_link_local == ipaddress.IPv6Interface(expected).ip


@pytest.mark.parametrize("command_output,expected", [(out_str1, "10.0.2.15"),
                                                     (out_str2, "127.0.0.1")])
def test_get_ipv4(mocker, command_output, expected):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=command_output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    obj.get_interface_ipv4addr(command_output)
    assert obj.ipv4 == ipaddress.IPv4Interface(expected).ip


@pytest.mark.parametrize("command_output,expected",
                         [(out_str4, "2001:730:1f:60a::cafe:106/64"),
                          (out_str5, "2002:0:c4:1::e:c0/128")])
def test_get_ipv6_prefixlen(mocker, command_output, expected):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=command_output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    obj.get_interface_ipv6addr(command_output)
    assert obj.prefixlen == ipaddress.IPv6Interface(expected)._prefixlen


@pytest.mark.parametrize("command_output,expected",
                         [(out_str1, "10.0.2.15/24"),
                          (out_str2, "127.0.0.1/8")])
def test_get_ipv4_netmask(mocker, command_output, expected):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=command_output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    obj.get_interface_ipv4addr(command_output)
    assert obj.netmask == ipaddress.IPv4Interface(expected).netmask


@pytest.mark.parametrize("command_output,expected",
                         [(out_str1, "10.0.2.15/24"),
                          (out_str2, "127.0.0.1/8")])
def test_get_ipv4_network(mocker, command_output, expected):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=command_output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    obj.get_interface_ipv4addr(command_output)
    assert obj.network == ipaddress.IPv4Interface(expected).network


@pytest.mark.parametrize("output, expected",
                         [(out_str4, "2001:730:1f:60a::cafe:106/64"),
                          (out_str5, "2002:0:c4:1::e:c0/128")])
def test_get_ipv6_network(mocker, output, expected):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    assert obj.network_v6 == ipaddress.IPv6Interface(expected).network


@pytest.mark.parametrize("output", [(out_str6)])
def test_get_ipv4_negative(mocker, output):
    mocker.patch.object(bft_iface,
                        '__init__',
                        return_value=None,
                        autospec=True)
    obj = bft_iface("dummy_dev", "dummy_iface", "dummy_cmd")
    with pytest.raises(BftIfaceNoIpV4Addr):
        assert obj.get_interface_ipv4addr(output)


@pytest.mark.parametrize("output", [(out_str6)])
def test_ipv4_negative(mocker, output):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")

    with pytest.raises(BftIfaceNoIpV4Addr):
        print(obj.ipv4)


@pytest.mark.parametrize("output, exp_ip, exp_netmask",
                         [(out_str7, "10.3.0.21", "10.3.0.21/24")])
def test_ipv4(mocker, output, exp_ip, exp_netmask):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")

    assert obj.ipv4 == ipaddress.IPv4Interface(exp_ip).ip
    assert obj.netmask == ipaddress.IPv4Interface(exp_netmask).netmask


@pytest.mark.parametrize("output", [(out_str7)])
def test_get_interface_ipv6addr_negative(mocker, output):
    mocker.patch.object(bft_iface,
                        '__init__',
                        return_value=None,
                        autospec=True)
    obj = bft_iface("dummy_dev", "dummy_iface", "dummy_cmd")
    with pytest.raises(BftIfaceNoIpV6Addr):
        assert obj.get_interface_ipv6addr(output)


@pytest.mark.parametrize("output", [(out_str7)])
def test_ipv6_negative(mocker, output):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")

    with pytest.raises(BftIfaceNoIpV6Addr):
        obj.ipv6


@pytest.mark.parametrize(
    "output, exp_ip, exp_net, exp_ip_link",
    [(out_str6, "2002:0:c4:1::e:c0", "2002:0:c4:1::e:c0/128", "fe80::6a02")])
def test_ipv6(mocker, output, exp_ip, exp_net, exp_ip_link):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=output,
                        autospec=True)
    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")

    assert obj.ipv6 == ipaddress.IPv6Interface(exp_ip).ip
    assert obj.network_v6 == ipaddress.IPv6Interface(exp_net).network
    assert obj.ipv6_link_local == ipaddress.IPv6Interface(exp_ip_link).ip


@pytest.mark.parametrize("output", [(out_str6), (out_str7)])
def test_refresh(mocker, output):
    dummy_dev = Dummy()
    mocker.patch.object(dummy_dev,
                        'check_output',
                        return_value=output,
                        autospec=True)
    mocker.patch.object(bft_iface,
                        'get_interface_macaddr',
                        return_value=None,
                        autospec=True)

    obj = bft_iface(dummy_dev, "dummy_iface", "dummy_cmd")
    obj.refresh()
