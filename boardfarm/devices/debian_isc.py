import ipaddress
import os
import re
import traceback

import pexpect
import six
from boardfarm.lib.common import retry_on_exception, scp_from
from boardfarm.lib.regexlib import ValidIpv4AddressRegex

from . import debian


class DebianISCProvisioner(debian.DebianBox):
    '''
    Linux based provisioner using ISC DHCP server
    '''

    model = ('debian-isc-provisioner')

    wan_cmts_provisioner = False
    standalone_provisioner = True
    wan_dhcp_server = False

    # default CM specific settings
    default_lease_time = 604800
    max_lease_time = 604800
    is_env_setup_done = False

    def __init__(self, *args, **kwargs):

        self.cm_network = ipaddress.IPv4Network(
            six.text_type(kwargs.pop('cm_network', "192.168.200.0/24")))
        self.cm_gateway = ipaddress.IPv4Address(
            six.text_type(kwargs.pop('cm_gateway', "192.168.200.1")))
        self.mta_network = ipaddress.IPv4Network(
            six.text_type(kwargs.pop('mta_network', "192.168.201.0/24")))
        self.mta_gateway = ipaddress.IPv4Address(
            six.text_type(kwargs.pop('mta_gateway', "192.168.201.1")))
        self.open_network = ipaddress.IPv4Network(
            six.text_type(kwargs.pop('open_network', "192.168.202.0/24")))
        self.open_gateway = ipaddress.IPv4Address(
            six.text_type(kwargs.pop('open_gateway', "192.168.202.1")))
        self.prov_network = ipaddress.IPv4Network(
            six.text_type(kwargs.pop('prov_network', "192.168.3.0/24")))
        self.prov_gateway = ipaddress.IPv4Address(
            six.text_type(kwargs.pop('prov_gateway', "192.168.3.222")))
        self.prov_ip = ipaddress.IPv4Address(
            six.text_type(kwargs.pop('prov_ip', "192.168.3.1")))

        self.prov_iface = ipaddress.IPv6Interface(
            six.text_type(
                kwargs.pop('prov_ipv6',
                           "2001:dead:beef:1::1/%s" % self.ipv6_prefix)))
        self.prov_ipv6, self.prov_nw_ipv6 = self.prov_iface.ip, self.prov_iface.network

        self.cm_gateway_v6_iface = ipaddress.IPv6Interface(
            six.text_type(
                kwargs.pop('cm_gateway_v6',
                           "2001:dead:beef:4::cafe/%s" % self.ipv6_prefix)))
        self.cm_gateway_v6, self.cm_network_v6 = self.cm_gateway_v6_iface.ip, self.cm_gateway_v6_iface.network
        self.cm_network_v6_start = ipaddress.IPv6Address(
            six.text_type(
                kwargs.pop('cm_network_v6_start', "2001:dead:beef:4::10")))
        self.cm_network_v6_end = ipaddress.IPv6Address(
            six.text_type(
                kwargs.pop('cm_network_v6_end', "2001:dead:beef:4::100")))
        self.open_gateway_iface = ipaddress.IPv6Interface(
            six.text_type(
                kwargs.pop('open_gateway_v6',
                           "2001:dead:beef:6::cafe/%s" % self.ipv6_prefix)))
        self.open_gateway_v6, self.open_network_v6 = self.open_gateway_iface.ip, self.open_gateway_iface.network
        self.open_network_v6_start = ipaddress.IPv6Address(
            six.text_type(
                kwargs.pop('open_network_v6_start', "2001:dead:beef:6::10")))
        self.open_network_v6_end = ipaddress.IPv6Address(
            six.text_type(
                kwargs.pop('open_network_v6_end', "2001:dead:beef:6::100")))
        self.prov_gateway_v6 = ipaddress.IPv6Address(
            six.text_type(
                kwargs.pop('prov_gateway_v6', "2001:dead:beef:1::cafe")))

        # we're storing a list of all /56 subnets possible from erouter_net_iface.
        # As per docsis, /56 must be the default pd length
        self.erouter_net_iface = ipaddress.IPv6Interface(
            six.text_type(kwargs.pop('erouter_net',
                                     "2001:dead:beef:e000::/51")))
        self.erouter_net = list(
            self.erouter_net_iface.network.subnets(
                56 - self.erouter_net_iface._prefixlen))

        self.sip_fqdn = kwargs.pop(
            'sip_fqdn', u"08:54:43:4F:4D:4C:41:42:53:03:43:4F:4D:00")
        self.time_server = ipaddress.IPv4Address(
            six.text_type(kwargs.pop('time_server', str(self.prov_ip))))
        self.timezone = self.get_timzone_offset(
            six.text_type(kwargs.pop('timezone', "UTC")))
        self.syslog_server = ipaddress.IPv4Address(
            six.text_type(kwargs.pop('syslog_server', str(self.prov_ip))))
        if 'options' in kwargs:
            options = [x.strip() for x in kwargs['options'].split(',')]
            for opt in options:
                # Not a well supported config, will go away at some point
                if opt.startswith('wan-cmts-provisioner'):
                    self.wan_cmts_provisioner = True
                    self.shared_tftp_server = True
                    # This does run one.. but it's handled via the provisioning code path
                    self.standalone_provisioner = False

        self.gw = self.prov_ip
        self.gwv6 = self.prov_ipv6
        self.nw = self.prov_network
        return super(DebianISCProvisioner, self).__init__(*args, **kwargs)

    def setup_dhcp6_config(self, board_config):
        tftp_server = self.tftp_device.tftp_server_ipv6_int()

        to_send = '''cat > /etc/dhcp/dhcpd6.conf-''' + board_config.get_station(
        ) + '''.master << EOF
preferred-lifetime 7200;
option dhcp-renewal-time 3600;
option dhcp-rebinding-time 5400;

allow leasequery;
prefix-length-mode prefer;

option dhcp6.info-refresh-time 21600;
option dhcp6.ia_pd code 25 = { integer 32, integer 32, integer 32, integer 16, integer 16, integer 32, integer 32, integer 8, ip6-address};
option dhcp6.gateway code 32003 = ip6-address;
option space docsis code width 2 length width 2;
option docsis.device-type code 2 = text;
option docsis.tftp-servers code 32 = array of ip6-address;
option docsis.configuration-file code 33 = text;
option docsis.syslog-servers code 34 = array of ip6-address;
option docsis.device-id code 36 = string;
option docsis.time-servers code 37 = array of ip6-address;
option docsis.time-offset code 38 = signed integer 32;
option docsis.cm-mac-address code 1026 = string;
option docsis.PKTCBL-CCCV4 code 2170 = { integer 16, integer 16, ip-address, integer 16, integer 16, ip-address };
option vsio.docsis code 4491 = encapsulate docsis;

# TODO: move to host section
option dhcp6.aftr-name  code 64 = string ;
# aftr-name aftr.boardfarm.com
option dhcp6.aftr-name 04:61:66:74:72:09:62:6f:61:72:64:66:61:72:6d:03:63:6F:6D:00;
option dhcp6.name-servers ###PROV_IPV6###;
option dhcp6.domain-search "boardfarm.com";

class "CM" {
  match if option docsis.device-type = "ECM";
}
class "EROUTER" {
  match if option docsis.device-type = "EROUTER";
}

subnet6 ###PROV_NW_IPV6### {
  interface ###IFACE###;
  ignore booting;
}

shared-network boardfarm {
  interface ###IFACE###;
    subnet6 ###CM_NETWORK_V6### {
        pool6 {
            range6 ###CM_NETWORK_V6_START### ###CM_NETWORK_V6_END###;
            allow members of "CM";
            option docsis.time-servers ###PROV_IPV6###;
            option docsis.syslog-servers ###PROV_IPV6### ;
            option docsis.time-offset 5000;
            option docsis.PKTCBL-CCCV4 1 4 ###MTA_DHCP_SERVER1### 2 4 ###MTA_DHCP_SERVER2###;
            option docsis.time-offset ###TIMEZONE###;
        }'''

        if self.cm_network_v6 != self.open_network_v6:
            to_send = to_send + '''
    }
    subnet6 ###OPEN_NETWORK_V6### {'''

        to_send = to_send + '''
        pool6 {
            range6 ###OPEN_NETWORK_V6_START### ###OPEN_NETWORK_V6_END###;
            allow members of "EROUTER";
            option dhcp6.solmax-rt   240;
            option dhcp6.inf-max-rt  360;
            prefix6 ###EROUTER_NET_START### ###EROUTER_NET_END### /###EROUTER_PREFIX###;
        }
        pool6 {
            range6 ###OPEN_NETWORK_HOST_V6_START### ###OPEN_NETWORK_HOST_V6_END###;
            allow unknown-clients;
            option dhcp6.solmax-rt   240;
            option dhcp6.inf-max-rt  360;
        }
    }
}
EOF'''

        to_send = to_send.replace('###IFACE###', self.iface_dut)
        to_send = to_send.replace('###PROV_IPV6###', str(self.prov_ipv6))
        to_send = to_send.replace('###PROV_NW_IPV6###', str(self.prov_nw_ipv6))
        to_send = to_send.replace('###CM_NETWORK_V6###',
                                  str(self.cm_network_v6))
        to_send = to_send.replace('###CM_NETWORK_V6_START###',
                                  str(self.cm_network_v6_start))
        to_send = to_send.replace('###CM_NETWORK_V6_END###',
                                  str(self.cm_network_v6_end))
        to_send = to_send.replace('###OPEN_NETWORK_V6###',
                                  str(self.open_network_v6))
        to_send = to_send.replace('###OPEN_NETWORK_V6_START###',
                                  str(self.open_network_v6_start))
        to_send = to_send.replace('###OPEN_NETWORK_V6_END###',
                                  str(self.open_network_v6_end))
        # Increment IP by 200 hosts
        to_send = to_send.replace('###OPEN_NETWORK_HOST_V6_START###',
                                  str(self.open_network_v6_start + 256 * 2))
        to_send = to_send.replace('###OPEN_NETWORK_HOST_V6_END###',
                                  str(self.open_network_v6_end + 256 * 2))

        # keep last ten /56 prefix in erouter pool. for unknown hosts
        to_send = to_send.replace('###EROUTER_NET_START###',
                                  str(self.erouter_net[-10].network_address))
        to_send = to_send.replace('###EROUTER_NET_END###',
                                  str(self.erouter_net[-1].network_address))
        to_send = to_send.replace('###EROUTER_PREFIX###',
                                  str(self.erouter_net[-1]._prefixlen))
        to_send = to_send.replace('###MTA_DHCP_SERVER1###', str(self.prov_ip))
        to_send = to_send.replace('###MTA_DHCP_SERVER2###', str(self.prov_ip))
        to_send = to_send.replace('###TIMEZONE###', str(self.timezone))
        # TODO: add ranges for subnet's, syslog server per CM

        self.sendline(to_send)
        self.expect(self.prompt)

        self.sendline('rm /etc/dhcp/dhcpd6.conf.'
                      '' + board_config.get_station())
        self.expect(self.prompt)

        cfg_file = "/etc/dhcp/dhcpd6.conf-" + board_config.get_station()

        # zero out old config
        self.sendline('cp /dev/null %s' % cfg_file)
        self.expect(self.prompt)

        # insert tftp server, TODO: how to clean up?
        if 'options' not in board_config['extra_provisioning_v6']['cm']:
            board_config['extra_provisioning_v6']['cm']['options'] = {}
        board_config['extra_provisioning_v6']['cm']['options'][
            'docsis.tftp-servers'] = tftp_server
        board_config['extra_provisioning_v6']['cm']['options'][
            'docsis.PKTCBL-CCCV4'] = "1 4 %s 1 4 %s" % (self.prov_ip,
                                                        self.prov_ip)

        # the IPv6 subnet for erouter_net in json, should be large enough
        # len(erouter_net) >= no. of boards + 10
        board_config['extra_provisioning_v6']['erouter']['fixed-prefix6'] = str(
            self.erouter_net[int(board_config.get_station().split("-")[-1]) %
                             len(self.erouter_net)])

        # there is probably a better way to construct this file...
        for dev, cfg_sec in board_config['extra_provisioning_v6'].items():
            self.sendline("echo 'host %s-%s {' >> %s" %
                          (dev, board_config.get_station(), cfg_file))
            for key, value in cfg_sec.items():
                if key == "options":
                    for k2, v2 in value.items():
                        self.sendline("echo '   option %s %s;' >> %s" %
                                      (k2, v2, cfg_file))
                        self.expect(self.prompt)
                else:
                    self.sendline("echo '   %s %s;' >> %s" %
                                  (key, value, cfg_file))
                    self.expect(self.prompt)
            self.sendline("echo '}' >> %s" % cfg_file)

        self.sendline('mv ' + cfg_file + ' /etc/dhcp/dhcpd6.conf.' +
                      board_config.get_station())
        self.expect(self.prompt)

        # can't provision without this, so let's ignore v6 if that's the case
        if tftp_server is None or self.dev.board.cm_cfg.cm_configmode == 'ipv4':
            self.sendline('rm /etc/dhcp/dhcpd6.conf.' +
                          board_config.get_station())
            self.expect(self.prompt)

        # combine all configs into one
        self.sendline("cat /etc/dhcp/dhcpd6.conf.* >> /etc/dhcp/dhcpd6.conf-" +
                      board_config.get_station() + ".master")
        self.expect(self.prompt)
        self.sendline("mv /etc/dhcp/dhcpd6.conf-" +
                      board_config.get_station() +
                      ".master /etc/dhcp/dhcpd6.conf")
        self.expect(self.prompt)

    def setup_dhcp_config(self, board_config):
        tftp_server = self.tftp_device.tftp_server_ip_int()

        to_send = '''cat > /etc/dhcp/dhcpd.conf-''' + board_config.get_station(
        ) + '''.master << EOF
log-facility local7;
option log-servers ###LOG_SERVER###;
option time-servers ###TIME_SERVER###;
default-lease-time 604800;
max-lease-time 604800;
allow leasequery;

class "CM" {
  match if substring (option vendor-class-identifier, 0, 6) = "docsis";
}
class "MTA" {
  match if substring (option vendor-class-identifier, 0, 4) = "pktc";
}
class "HOST" {
  match if ((substring(option vendor-class-identifier,0,6) != "docsis") and (substring(option vendor-class-identifier,0,4) != "pktc"));
}

option space docsis-mta;
option docsis-mta.dhcp-server-1 code 1 = ip-address;
option docsis-mta.dhcp-server-2 code 2 = ip-address;
option docsis-mta.provision-server code 3 = { integer 8, string };
option docsis-mta.kerberos-realm code 6 = string;
option docsis-mta.as-req-as-rep-1 code 4 = { integer 32, integer 32, integer 32 };
option docsis-mta.as-req-as-rep-2 code 5 = { integer 32, integer 32, integer 32 };
option docsis-mta.krb-realm-name code 6 = string;
option docsis-mta.tgs-util code 7 = integer 8;
option docsis-mta.timer code 8 = integer 8;
option docsis-mta.ticket-ctrl-mask code 9 = integer 16;
option docsis-mta-pkt code 122 = encapsulate docsis-mta;

subnet ###PROV_IP### netmask ###PROV_NETMASK### {
  interface ###IFACE###;
  ignore booting;
}

shared-network boardfarm {
  interface ###IFACE###;
  subnet ###CM_IP### netmask ###CM_NETMASK###
  {
    option routers ###CM_GATEWAY###;
    option broadcast-address ###CM_BROADCAST###;
    option dhcp-parameter-request-list 43;
    option domain-name "local";
    option time-offset ###TIMEZONE###;
    option docsis-mta.dhcp-server-1 ###MTA_DHCP_SERVER1###;
    option docsis-mta.dhcp-server-2 ###MTA_DHCP_SERVER2###;
  }
  subnet ###MTA_IP### netmask ###MTA_NETMASK###
  {
    option routers ###MTA_GATEWAY###;
    option broadcast-address ###MTA_BROADCAST###;
    option time-offset ###TIMEZONE###;
    option domain-name-servers ###WAN_IP###;
    option docsis-mta.kerberos-realm 05:42:41:53:49:43:01:31:00 ;
    option docsis-mta.provision-server 0 ###MTA_SIP_FQDN### ;
  }
  subnet ###OPEN_IP### netmask ###OPEN_NETMASK###
  {
    option routers ###OPEN_GATEWAY###;
    option broadcast-address ###OPEN_BROADCAST###;
    option domain-name "local";
    option time-offset ###TIMEZONE###;
    option domain-name-servers ###WAN_IP###;
  }
  pool {
    range ###MTA_START_RANGE### ###MTA_END_RANGE###;
    allow members of "MTA";
  }
  pool {
    range ###CM_START_RANGE### ###CM_END_RANGE###;
    allow members of "CM";
  }
  pool {
    range ###OPEN_START_RANGE### ###OPEN_END_RANGE###;
    allow members of "HOST";
  }
}
EOF'''

        to_send = to_send.replace('###LOG_SERVER###', str(self.syslog_server))
        to_send = to_send.replace('###TIME_SERVER###', str(self.time_server))
        to_send = to_send.replace('###MTA_SIP_FQDN###', str(self.sip_fqdn))
        to_send = to_send.replace('###NEXT_SERVER###', str(self.prov_ip))
        to_send = to_send.replace('###IFACE###', str(self.iface_dut))
        to_send = to_send.replace('###MTA_DHCP_SERVER1###', str(self.prov_ip))
        to_send = to_send.replace('###MTA_DHCP_SERVER2###', str(self.prov_ip))
        to_send = to_send.replace('###PROV###', str(self.prov_ip))
        to_send = to_send.replace('###PROV_IP###', str(self.prov_network[0]))
        to_send = to_send.replace('###PROV_NETMASK###',
                                  str(self.prov_network.netmask))
        to_send = to_send.replace('###CM_IP###', str(self.cm_network[0]))
        to_send = to_send.replace('###CM_NETMASK###',
                                  str(self.cm_network.netmask))
        to_send = to_send.replace('###CM_START_RANGE###',
                                  str(self.cm_network[10]))
        to_send = to_send.replace('###CM_END_RANGE###',
                                  str(self.cm_network[60]))
        to_send = to_send.replace('###CM_GATEWAY###', str(self.cm_gateway))
        to_send = to_send.replace('###CM_BROADCAST###',
                                  str(self.cm_network[-1]))
        to_send = to_send.replace('###DEFAULT_TFTP_SERVER###',
                                  str(self.prov_ip))
        to_send = to_send.replace('###MTA_IP###', str(self.mta_network[0]))
        to_send = to_send.replace('###MTA_NETMASK###',
                                  str(self.mta_network.netmask))
        to_send = to_send.replace('###MTA_START_RANGE###',
                                  str(self.mta_network[10]))
        to_send = to_send.replace('###MTA_END_RANGE###',
                                  str(self.mta_network[60]))
        to_send = to_send.replace('###MTA_GATEWAY###', str(self.mta_gateway))
        to_send = to_send.replace('###MTA_BROADCAST###',
                                  str(self.mta_network[-1]))
        to_send = to_send.replace('###OPEN_IP###', str(self.open_network[0]))
        to_send = to_send.replace('###OPEN_NETMASK###',
                                  str(self.open_network.netmask))
        to_send = to_send.replace('###OPEN_START_RANGE###',
                                  str(self.open_network[10]))
        to_send = to_send.replace('###OPEN_END_RANGE###',
                                  str(self.open_network[60]))
        to_send = to_send.replace('###OPEN_GATEWAY###', str(self.open_gateway))
        to_send = to_send.replace('###OPEN_BROADCAST###',
                                  str(self.open_network[-1]))
        to_send = to_send.replace('###TIMEZONE###', str(self.timezone))

        to_send = to_send.replace('###WAN_IP###', str(tftp_server))

        self.sendline(to_send)
        self.expect(self.prompt)

        self.sendline('rm /etc/dhcp/dhcpd.conf.'
                      '' + board_config.get_station())
        self.expect(self.prompt)

        cfg_file = "/etc/dhcp/dhcpd.conf-" + board_config.get_station()

        # zero out old config
        self.sendline('cp /dev/null %s' % cfg_file)
        self.expect(self.prompt)

        # insert tftp server, TODO: how to clean up?
        board_config['extra_provisioning']['cm']['next-server'] = tftp_server
        board_config['extra_provisioning']['mta']['next-server'] = tftp_server

        # there is probably a better way to construct this file...
        for dev, cfg_sec in board_config['extra_provisioning'].items():
            # skip only erouter for ipv6/bridge only
            if self.dev.board.cm_cfg.cm_configmode in (
                    'bridge', 'dslite', "ipv6") and dev == 'erouter':
                continue
            self.sendline("echo 'host %s-%s {' >> %s" %
                          (dev, board_config.get_station(), cfg_file))
            for key, value in cfg_sec.items():
                if key == "options":
                    for k2, v2 in value.items():
                        self.sendline("echo '   option %s %s;' >> %s" %
                                      (k2, v2, cfg_file))
                        self.expect(self.prompt)
                else:
                    self.sendline("echo '   %s %s;' >> %s" %
                                  (key, value, cfg_file))
                    self.expect(self.prompt)
            self.sendline("echo '}' >> %s" % cfg_file)

        self.sendline('mv ' + cfg_file + ' /etc/dhcp/dhcpd.conf.' +
                      board_config.get_station())
        self.expect(self.prompt)

        if tftp_server is None:
            self.sendline('rm /etc/dhcp/dhcpd.conf.' +
                          board_config.get_station())
            self.expect(self.prompt)

        # combine all configs into one
        self.sendline("cat /etc/dhcp/dhcpd.conf.* >> /etc/dhcp/dhcpd.conf-" +
                      board_config.get_station() + ".master")
        self.expect(self.prompt)
        self.sendline("mv /etc/dhcp/dhcpd.conf-" + board_config.get_station() +
                      ".master /etc/dhcp/dhcpd.conf")
        self.expect(self.prompt)

    def get_timzone_offset(self, timezone):
        if timezone == "UTC":
            return 0
        if timezone.startswith("GMT") or timezone.startswith("UTC"):
            try:
                offset = int(re.search(r"[\W\D\S]?\d{1,2}", timezone).group(0))
            except:
                # In case a value was not provided, will throw an Attribute error
                return 0
            # offset should be from GMT -11 to GMT 12
            if offset in range(-11, 13):
                return 3600 * offset
            else:
                print("Invalid Timezone. Using UTC standard")
                return 0

    # TODO: This needs to be pushed to boardfarm-docsis at a later stage
    def update_cmts_isc_dhcp_config(self, board_config):
        if 'extra_provisioning' not in board_config:
            # same defaults so we at least set tftp server to WAN
            board_config['extra_provisioning'] = {}
        if 'extra_provisioning_v6' not in board_config:
            board_config['extra_provisioning_v6'] = {}

        tftp_server = self.tftp_device.tftp_server_ip_int()
        sip_server = [
            re.search('wan-static-ip:' + '(' + ValidIpv4AddressRegex + ')',
                      i['options']).group(1) for i in board_config['devices']
            if 'sipcenter' in i['name']
        ][0]
        # This can be later broken down to smaller chunks to add options specific to type of device.
        mta_dhcp_options = {
            "mta": {
                "hardware ethernet": board_config['mta_mac'],
                "filename": "\"" + self.dev.board.mta_cfg.encoded_fname + "\"",
                "options": {
                    "bootfile-name":
                    "\"" + self.dev.board.mta_cfg.encoded_fname + "\"",
                    "dhcp-parameter-request-list": "3, 6, 7, 12, 15, 43, 122",
                    "domain-name": "\"sipcenter.com\"",
                    "domain-name-servers": "%s" % sip_server,
                    "routers": self.mta_gateway,
                    "log-servers": self.prov_ip,
                    "host-name": "\"" + board_config.get_station() + "\""
                }
            }
        }
        board_config["extra_provisioning"].update(mta_dhcp_options)

        # This can be later broken down to smaller chunks to add options specific to type of device.
        cm_dhcp_options = {
            "cm": {
                "hardware ethernet": board_config['cm_mac'],
                "filename": "\"" + self.dev.board.cm_cfg.encoded_fname + "\"",
                "options": {
                    "bootfile-name":
                    "\"" + self.dev.board.cm_cfg.encoded_fname + "\"",
                    "dhcp-parameter-request-list":
                    "2, 3, 4, 6, 7, 12, 43, 122",
                    "docsis-mta.dhcp-server-1": self.prov_ip,
                    "docsis-mta.dhcp-server-2": self.prov_ip,
                    "docsis-mta.provision-server":
                    "0 08:54:43:4F:4D:4C:41:42:53:03:43:4F:4D:00",
                    "docsis-mta.kerberos-realm": "05:42:41:53:49:43:01:31:00",
                    "domain-name-servers": "%s" % tftp_server,
                    "time-offset": "%s" % str(self.timezone)
                }
            }
        }
        board_config["extra_provisioning"].update(cm_dhcp_options)

        board_config['extra_provisioning']["erouter"] = \
            {"hardware ethernet": board_config['erouter_mac'],
              "default-lease-time": self.default_lease_time,
              "max-lease-time": self.max_lease_time,
                  "options": {"domain-name-servers": "%s" % tftp_server}
            }

        # This can be later broken down to another method which adds dhcpv6 options to type of device.
        tftp_server = self.tftp_device.tftp_server_ipv6_int()
        board_config['extra_provisioning_v6']["cm"] = \
            {"host-identifier option dhcp6.client-id": '00:03:00:01:' + board_config['cm_mac'],
              "options": {"docsis.configuration-file": '"%s"' % self.dev.board.cm_cfg.encoded_fname,
                  "dhcp6.name-servers": "%s" % tftp_server
                }
            }
        board_config['extra_provisioning_v6']["erouter"] = \
            {"host-identifier option dhcp6.client-id": '00:03:00:01:' + board_config['erouter_mac'],
                "hardware ethernet": board_config['erouter_mac'],
                "options": {
                    "dhcp6.name-servers": "%s" % tftp_server
                }
            }

        self.setup_dhcp_config(board_config)
        self.setup_dhcp6_config(board_config)

    # this needs to be cleaned up a bit. Other devices should use this method to configure a dhcp server.
    # e.g. debian won't require start dhcp_server_server method. it should call this static method.
    # this will help in removing reprovision_board at a later time.
    @staticmethod
    def setup_dhcp_env(device):
        device.install_pkgs()
        device.sendline('/etc/init.d/rsyslog start')
        device.expect(device.prompt)

        # if we are not a full blown wan+provisoner then offer to route traffic
        if not device.wan_cmts_provisioner:
            device.setup_as_wan_gateway()
        ''' Setup DHCP and time server etc for CM provisioning'''
        device.sendline(
            'echo INTERFACESv4="%s" > /etc/default/isc-dhcp-server' %
            device.iface_dut)
        device.expect(device.prompt)
        device.sendline(
            'echo INTERFACESv6="%s" >> /etc/default/isc-dhcp-server' %
            device.iface_dut)
        device.expect(device.prompt)
        # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
        device.sendline('sysctl -w net.ipv6.conf.%s.accept_dad=0' %
                        device.iface_dut)
        device.expect(device.prompt)
        if not device.wan_no_eth0:
            device.sendline('ifconfig %s up' % device.iface_dut)
            device.expect(device.prompt)
            device.sendline('ifconfig %s %s' % (device.iface_dut, device.gw))
            device.expect(device.prompt)

            # TODO: we need to route via eth0 at some point
            # TODO: don't hard code eth0...
            device.disable_ipv6('eth0')
            device.enable_ipv6(device.iface_dut)
            if device.gwv6 is not None:
                device.sendline(
                    'ip -6 addr add %s/%s dev %s' %
                    (device.gwv6, device.ipv6_prefix, device.iface_dut))
                device.expect(device.prompt)

        if device.static_route is not None:
            device.sendline('ip route add %s' % device.static_route)
            device.expect(device.prompt)

        for nw in [device.cm_network, device.mta_network, device.open_network]:
            device.sendline('ip route add %s via %s' %
                            (nw, device.prov_gateway))
            device.expect(device.prompt)

        for nw in [device.cm_gateway_v6, device.open_gateway_v6]:
            device.sendline('ip -6 route add %s/%s via %s dev %s' %
                            (nw, device.ipv6_prefix, device.prov_gateway_v6,
                             device.iface_dut))
            device.expect(device.prompt)

        for nw in device.erouter_net:
            device.sendline('ip -6 route add %s via %s' %
                            (nw, device.prov_gateway_v6))
            device.expect(device.prompt)

        # only start tftp server if we are a full blown wan+provisioner
        if device.wan_cmts_provisioner:
            device.start_tftp_server()

        device.sendline(
            "sed 's/disable\\t\\t= yes/disable\\t\\t= no/g' -i /etc/xinetd.d/time"
        )
        device.expect(device.prompt)
        device.sendline(
            "grep -q flags.*=.*IPv6 /etc/xinetd.d/time || sed '/wait.*=/a\\\\tflags\\t\\t= IPv6' -i /etc/xinetd.d/time"
        )
        device.expect(device.prompt)
        device.sendline('/etc/init.d/xinetd restart')
        device.expect('Starting internet superserver: xinetd.')
        device.expect(device.prompt)
        device.is_env_setup_done = True

    def print_dhcp_config(self):
        self.sendline('cat /etc/dhcp/dhcpd.conf')
        self.sendline('cat /etc/dhcp/dhcpd.conf')
        self.expect(self.prompt)
        self.sendline('cat /etc/dhcp/dhcpd6.conf')
        self.expect_exact('cat /etc/dhcp/dhcpd6.conf')
        self.expect(self.prompt)
        return ""

    # this should be renamed to a more suitable generic name.
    def provision_board(self, board_config):
        '''
        Reprovisions current board with new CM cfg
        '''
        exc_to_raise = None
        check = False
        for i in range(3):
            try:
                self.take_lock('/etc/init.d/isc-dhcp-server.lock')

                print_config = False
                if not self.is_env_setup_done:
                    DebianISCProvisioner.setup_dhcp_env(self)
                    print_config = True

                # this is the chunk from reprovision
                self.update_cmts_isc_dhcp_config(board_config)
                self._restart_dhcp()
                check = True
            except Exception as e:
                exc_to_raise = e
                self.expect(pexpect.TIMEOUT, timeout=(i * 20))
            finally:
                self.sendcontrol('c')
                self.release_lock('/etc/init.d/isc-dhcp-server.lock')
                self.sendline('rm /etc/init.d/isc-dhcp-server.lock')
                self.expect(self.prompt)
            if check:
                break
        else:
            raise exc_to_raise
        if print_config:
            self.print_dhcp_config()

    def reprovision_board(self, board_config):
        '''
        This should not be used, and will go away
        '''
        self.provision_board(board_config)

    def _try_to_restart_dhcp(self, do_ipv6):
        self.sendline('/etc/init.d/isc-dhcp-server restart')
        matching = [
            'Starting ISC DHCP(v4)? server.*dhcpd.',
            'Starting isc-dhcp-server.*'
        ]
        match_num = 1
        if do_ipv6:
            matching.append('Starting ISC DHCPv6 server: dhcpd(6)?.\r\n')
            match_num += 1
        else:
            print(
                "NOTE: not starting IPv6 because this provisioner is not setup properly"
            )

        for not_used in range(match_num):
            self.expect(matching)
            match_num -= 1
        self.expect(self.prompt)
        return match_num

    def _restart_dhcp(self):
        do_ipv6 = True

        try:
            chk_ip = self.get_interface_ip6addr(self.iface_dut)
            if ipaddress.IPv6Address(
                    six.text_type(chk_ip)) not in self.prov_nw_ipv6:
                do_ipv6 = False
            if self.tftp_device.tftp_server_ipv6_int() is None:
                do_ipv6 = False
        except:
            do_ipv6 = False

        match_num = retry_on_exception(self._try_to_restart_dhcp, (do_ipv6, ))

        if match_num != 0:
            self.sendline('tail /var/log/syslog -n 100')
            self.expect(self.prompt)
            self.sendline('cat /etc/dhcp/dhcpd.conf')
            self.expect(self.prompt)
            self.sendline('cat /etc/dhcp/dhcpd6.conf')
            self.expect(self.prompt)
        assert match_num == 0, "Incorrect number of DHCP servers started, something went wrong!"

        self.sendline('ps aux | grep dhcpd; echo DONE')
        self.expect_exact('ps aux | grep dhcpd; echo DONE')
        self.expect('DONE')

        assert len(re.findall(
            'dhcpd[^\n]*-4',
            self.before)) == 1, "Wrong number of DHCP4 servers running"
        assert len(re.findall(
            'dhcpd[^\n]*-6',
            self.before)) == 1, "Wrong number of DHCP6 servers running"
        self.expect(self.prompt)

    def get_attr_from_dhcp(self,
                           attr,
                           exp_pattern,
                           dev,
                           station,
                           match_group=4):
        '''Try getting an attribute from the dhcpd.conf.<station> file'''
        val = None
        try:
            self.sendline('cat  /etc/dhcp/dhcpd.conf.%s' % station)
            idx = self.expect([
                '(%s-%s\s\{([^}]+)(%s\s(%s))\;)' %
                (dev, station, attr, exp_pattern)
            ] + ['No such file or directory'] + [pexpect.TIMEOUT],
                              timeout=10)
            if idx == 0:
                # the value should be in group 4
                val = self.match.group(match_group)
        except:
            pass
        return val

    def get_cfgs(self, board_config):
        '''Tries to get the cfg out of the dhcpd.conf for the station in question'''
        try:
            mta_cfg = self.get_attr_from_dhcp('filename', '".*?"', 'mta',
                                              board_config.get_station())
            mta_cfg_srv = self.get_attr_from_dhcp('next-server',
                                                  ValidIpv4AddressRegex, 'mta',
                                                  board_config.get_station())

            cm_cfg = self.get_attr_from_dhcp('filename', '".*?"', 'cm',
                                             board_config.get_station())
            cm_cfg_srv = self.get_attr_from_dhcp('next-server',
                                                 ValidIpv4AddressRegex, 'cm',
                                                 board_config.get_station())
            if mta_cfg is None or mta_cfg_srv is None or cm_cfg is None or cm_cfg_srv is None:
                raise
            return [[mta_cfg.replace('"', ''), mta_cfg_srv],
                    [cm_cfg.replace('"', ''), cm_cfg_srv]]
        except:
            pass

        return None

    def get_conf_file_from_tftp(self, _tmpdir, board_config):
        '''Retrieve the files in the cfg_list from the tftp sever, puts them in localhost:/tmp/'''

        cfg_list = self.get_cfgs(board_config)
        if cfg_list is None:
            return False

        for elem in cfg_list:
            conf_file = self.tftp_dir + '/' + elem[0]
            server = elem[1]

            # this is where the current (to be downloaded from the tftp)
            # config is going to be placed
            dest_fname = _tmpdir + '/' + os.path.basename(
                conf_file) + "." + board_config.get_station() + ".current"
            try:
                os.remove(dest_fname)
            except:
                pass

            try:
                print('Downloading ' + server + ':' + conf_file + ' to ' +
                      dest_fname)
                scp_from(conf_file, server, self.tftp_device.username,
                         self.tftp_device.password, self.tftp_device.port,
                         dest_fname)

                if not os.path.isfile(dest_fname):
                    # Something has gone wrong as the tftp client has not thrown an
                    # exception, but the file is not where it should be!!
                    print(
                        "Tftp completed but %s not found in destination dir: "
                        % dest_fname)
                    return False
                print("Downloaded: " + conf_file)
            except:
                print("Failed to download %s from %s" %
                      (conf_file, self.ipaddr))
                return False

        return True

    def get_ipv4_time_server(self):
        return self.time_server

    def get_aftr_name(self):
        return 'aftr.boardfarm.com'

    def send(self, s):
        bad_commands = ['ifconfig %s down' % self.iface_dut]

        for cmd in bad_commands:
            if cmd in s:
                traceback.print_exc()
                raise Exception("ERROR: can not turn off shared interface!")

        super(DebianISCProvisioner, self).send(s)

    def check_status(self):
        self.sendline('cat /var/log/syslog | grep dhcpd | tail -n 100')
        self.expect(self.prompt)
        super(DebianISCProvisioner, self).check_status()
