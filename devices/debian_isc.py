import ipaddress
import os
import pexpect
from lib.regexlib import ValidIpv4AddressRegex
from lib.docsis import docsis, cm_cfg

from devices import DebianBox

class DebianISCProvisioner(DebianBox):
    '''
    Linux based provisioner using ISC DHCP server
    '''

    model = ('debian-isc-provisioner')

    wan_cmts_provisioner = False
    standalone_provisioner = True

    def __init__(self, *args, **kwargs):

        self.cm_network = ipaddress.IPv4Network(kwargs.pop('cm_network', u"192.168.200.0/24"))
        self.cm_gateway = ipaddress.IPv4Address(kwargs.pop('cm_gateway', u"192.168.200.1"))
        self.mta_network = ipaddress.IPv4Network(kwargs.pop('mta_network', u"192.168.201.0/24"))
        self.mta_gateway = ipaddress.IPv4Address(kwargs.pop('mta_gateway', u"192.168.201.1"))
        self.open_network = ipaddress.IPv4Network(kwargs.pop('open_network', u"192.168.202.0/24"))
        self.open_gateway = ipaddress.IPv4Address(kwargs.pop('open_gateway', u"192.168.202.1"))
        self.prov_network = ipaddress.IPv4Network(kwargs.pop('prov_network', u"192.168.3.0/24"))
        self.prov_gateway = ipaddress.IPv4Address(kwargs.pop('prov_gateway', u"192.168.3.222"))
        self.prov_ip = ipaddress.IPv4Address(kwargs.pop('prov_ip', u"192.168.3.1"))

        if 'options' in kwargs:
            options = [x.strip() for x in kwargs['options'].split(',')]
            for opt in options:
                # Not a well supported config, will go away at some point
                if opt.startswith('wan-cmts-provisioner'):
                    self.wan_cmts_provisioner = True
                    self.shared_tftp_server = True
                    # This does run one.. but it's handled via the provisioning code path
                    self.wan_dhcp_server = False
                    self.standalone_provisioner = False

        self.gw = self.prov_ip
        self.nw = self.prov_network
        return super(DebianISCProvisioner, self).__init__(*args, **kwargs)

    def update_cmts_isc_dhcp_config(self, board_config):
        tftp_server = self.tftp_device.tftp_server_ip_int()

        # TODO: lots of hard coded values... all need to go away
        to_send = '''cat > /etc/dhcp/dhcpd.conf-''' + board_config['station'] + '''.master << EOF
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
    option time-offset 1;
    option tftp-server-name "###DEFAULT_TFTP_SERVER###";
    option docsis-mta.dhcp-server-1 ###MTA_DHCP_SERVER1###;
    option docsis-mta.dhcp-server-2 ###MTA_DHCP_SERVER2###;
    filename "UNLIMITCASA.cfg";
  }
  subnet ###MTA_IP### netmask ###MTA_NETMASK###
  {
    option routers ###MTA_GATEWAY###;
    option broadcast-address ###MTA_BROADCAST###;
    option time-offset 1;
    option domain-name-servers ###PROV###;
    option docsis-mta.kerberos-realm 05:42:41:53:49:43:01:31:00 ;
    option docsis-mta.provision-server 0 08:54:43:4F:4D:4C:41:42:53:03:43:4F:4D:00 ;
  }
  subnet ###OPEN_IP### netmask ###OPEN_NETMASK###
  {
    option routers ###OPEN_GATEWAY###;
    option broadcast-address ###OPEN_BROADCAST###;
    option domain-name "local";
    option time-offset 1;
    option domain-name-servers ###PROV###;
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

        to_send = to_send.replace('###LOG_SERVER###', str(self.prov_ip))
        to_send = to_send.replace('###TIME_SERVER###', str(self.prov_ip))
        to_send = to_send.replace('###NEXT_SERVER###', str(self.prov_ip))
        to_send = to_send.replace('###IFACE###', str(self.iface_dut))
        to_send = to_send.replace('###MTA_DHCP_SERVER1###', str(self.prov_ip))
        to_send = to_send.replace('###MTA_DHCP_SERVER2###', str(self.prov_ip))
        to_send = to_send.replace('###PROV###', str(self.prov_ip))
        to_send = to_send.replace('###PROV_IP###', str(self.prov_network[0]))
        to_send = to_send.replace('###PROV_NETMASK###', str(self.prov_network.netmask))
        to_send = to_send.replace('###CM_IP###', str(self.cm_network[0]))
        to_send = to_send.replace('###CM_NETMASK###', str(self.cm_network.netmask))
        to_send = to_send.replace('###CM_START_RANGE###', str(self.cm_network[10]))
        to_send = to_send.replace('###CM_END_RANGE###', str(self.cm_network[60]))
        to_send = to_send.replace('###CM_GATEWAY###', str(self.cm_gateway))
        to_send = to_send.replace('###CM_BROADCAST###', str(self.cm_network[-1]))
        to_send = to_send.replace('###DEFAULT_TFTP_SERVER###', str(self.prov_ip))
        to_send = to_send.replace('###MTA_IP###', str(self.mta_network[0]))
        to_send = to_send.replace('###MTA_NETMASK###', str(self.mta_network.netmask))
        to_send = to_send.replace('###MTA_START_RANGE###', str(self.mta_network[10]))
        to_send = to_send.replace('###MTA_END_RANGE###', str(self.mta_network[60]))
        to_send = to_send.replace('###MTA_GATEWAY###', str(self.mta_gateway))
        to_send = to_send.replace('###MTA_BROADCAST###', str(self.mta_network[-1]))
        to_send = to_send.replace('###OPEN_IP###', str(self.open_network[0]))
        to_send = to_send.replace('###OPEN_NETMASK###', str(self.open_network.netmask))
        to_send = to_send.replace('###OPEN_START_RANGE###', str(self.open_network[10]))
        to_send = to_send.replace('###OPEN_END_RANGE###', str(self.open_network[60]))
        to_send = to_send.replace('###OPEN_GATEWAY###', str(self.open_gateway))
        to_send = to_send.replace('###OPEN_BROADCAST###', str(self.open_network[-1]))

        self.sendline(to_send)
	self.expect(self.prompt)

        # The board will ignore this unless the docsis-mac is set to ipv6
        # That needs to be done manually as well as copying any CM cfg files
        # to the provisioner (e.g. still not fully automated)
        # TODO: fix hard coded tftp ipv6 addr
#        self.sendline('''cat > /etc/dhcp/dhcpd6.conf-''' + board_config['station'] + '''.master << EOF
#preferred-lifetime 7500;
#option dhcp-renewal-time 3600;
#option dhcp-rebinding-time 5400;
#allow leasequery;
#option dhcp6.name-servers 2001:4860:4860::8888;
#option dhcp6.domain-search "test.example.com","example.com";
#option dhcp6.info-refresh-time 21600;
#option dhcp6.ia_pd code 25 = { integer 32, integer 32, integer 32, integer 16, integer 16, integer 32, integer 32, integer 8, ip6-address};
#option dhcp6.gateway code 32003 = ip6-address;
#option space docsis code width 2 length width 2 hash size 100;
#option docsis.tftp-servers code 32 = array of ip6-address;
#option docsis.configuration-file code 33 = text;
#option docsis.syslog-servers code 34 = array of ip6-address;
##option docsis.device-id code 36 = string;
#option docsis.time-servers code 37 = array of ip6-address;
#option docsis.time-offset code 38 = signed integer 32;
#option vsio.docsis code 4491 = encapsulate docsis;
#
#subnet6 2001:ed8:77b5:3::/64 {
#    range6 2001:ed8:77b5:3::10 2001:ed8:77b5:3::100;
#    interface %s;
#    option docsis.tftp-servers 2001:ed8:77b5:3::101;
#    option docsis.time-servers 2001:ed8:77b5:3::101;
#    option docsis.configuration-file "9_EU_CBN_IPv6_LG.cfg";
#    option docsis.syslog-servers 2001:ed8:77b5:3::101 ;
#    option docsis.time-offset 5000;
#}
#subnet6 2001:ed8:77b5:2000::/64 {
#    range6 2001:ed8:77b5:2000::10 2001:ed8:77b5:2000::100;
#    interface %s;
#    option docsis.tftp-servers 2001:ed8:77b5:3::101;
#    option docsis.time-servers 2001:ed8:77b5:3::101;
#    option docsis.configuration-file "9_EU_CBN_IPv6_LG.cfg";
#    option docsis.syslog-servers 2001:ed8:77b5:3::101;
#    option docsis.time-offset 5000;
#}
#subnet6 2001:ed8:77b5:2001::/64 {
#    range6 2001:ed8:77b5:2001::10 2001:ed8:77b5:2001::100;
#    interface %s;
#    option dhcp6.ia_pd 1234 20000 40000 26 25 30000 60000 64 2001:ed8:77b5:4::;
#    option dhcp6.solmax-rt   240;
#    option dhcp6.inf-max-rt  360;
#}
#EOF''' % (self.iface_dut, self.iface_dut, self.iface_dut))
#        self.expect(self.prompt)

        self.sendline('rm /etc/dhcp/dhcpd.conf.''' + board_config['station'])
        self.expect(self.prompt)

        if 'extra_provisioning' not in board_config:
            # same defaults so we at least set tftp server to WAN
            board_config['extra_provisioning'] = {}
            if 'mta_mac' in board_config:
                board_config['extra_provisioning']["mta"] = \
                    { "hardware ethernet": board_config['mta_mac'],
                     "options": { "domain-name": "\"sipcenter.com\"",
                                  "domain-name-servers": "%s" % self.prov_ip,
                                  "routers": "%s" % self.mta_gateway,
                                  "log-servers": "%s" % self.prov_ip,
                                  "host-name": "\"" + board_config['station'] + "\""
                                }
                    }
            else:
                board_config['extra_provisioning']["mta"] = {}
            if 'mta_mac' in board_config:
                board_config['extra_provisioning']["cm"] = \
                    { "hardware ethernet": board_config['cm_mac'],
                         "options": { "domain-name-servers": "%s" % self.prov_ip,
                                      "time-offset": "-25200"
                                    }
                    }
            else:
                board_config['extra_provisioning']["cm"] = {}

        cfg_file = "/etc/dhcp/dhcpd.conf-" + board_config['station']

        # zero out old config
        self.sendline('cp /dev/null %s' % cfg_file)
        self.expect(self.prompt)

        # insert tftp server, TODO: how to clean up?
        board_config['extra_provisioning']['cm']['next-server'] = tftp_server
        board_config['extra_provisioning']['mta']['next-server'] = tftp_server

        # there is probably a better way to construct this file...
        for dev, cfg_sec in board_config['extra_provisioning'].iteritems():
            self.sendline("echo 'host %s-%s {' >> %s" % (dev, board_config['station'], cfg_file))
            for key, value in cfg_sec.iteritems():
                if key == "options":
                    for k2, v2 in value.iteritems():
                        self.sendline("echo '   option %s %s;' >> %s" % (k2, v2, cfg_file))
                        self.expect(self.prompt)
                else:
                    self.sendline("echo '   %s %s;' >> %s" % (key, value, cfg_file))
                    self.expect(self.prompt)
            self.sendline("echo '}' >> %s" % cfg_file)

        # TODO: extra per board dhcp6 provisioning

        self.sendline('mv ' + cfg_file + ' /etc/dhcp/dhcpd.conf.' + board_config['station'])
        self.expect(self.prompt)
        # combine all configs into one
        self.sendline("cat /etc/dhcp/dhcpd.conf.* >> /etc/dhcp/dhcpd.conf-" + board_config['station'] + ".master")
        self.expect(self.prompt)
        self.sendline("mv /etc/dhcp/dhcpd.conf-" + board_config['station'] + ".master /etc/dhcp/dhcpd.conf")
        self.expect(self.prompt)

    def copy_cmts_provisioning_files(self, board_config):
        # Look in all overlays as well, and PATH as a workaround for standalone
        paths = os.environ['PATH'].split(os.pathsep)
        paths += os.environ['BFT_OVERLAY'].split(' ')
        cfg_list = []

        if 'tftp_cfg_files' in board_config:
            for cfg in board_config['tftp_cfg_files']:
                if isinstance(cfg, cm_cfg) or isinstance(cfg, mta_cfg):
                    cfg_list.append(cfg)
                else:
                    for path in paths:
                        cfg_list += glob.glob(path + '/devices/cm-cfg/%s' % cfg)
        else:
            for path in paths:
                cfg_list += glob.glob(path + '/devices/cm-cfg/UNLIMITCASA.cfg')
        cfg_set = set(cfg_list)

        # Copy binary files to tftp server
        for cfg in cfg_set:
            d = docsis(cfg)
            ret = d.encode()
            self.tftp_device.copy_file_to_server(ret)

    def provision_board(self, board_config):
        self.install_pkgs()

        # if we are not a full blown wan+provisoner then offer to route traffic
        if not self.wan_cmts_provisioner:
            self.setup_as_wan_gateway()

        ''' Setup DHCP and time server etc for CM provisioning'''
        self.sendline('sed s/INTERFACES=.*/INTERFACES=\\"%s\\"/g -i /etc/default/isc-dhcp-server' % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('sed s/INTERFACESv4=.*/INTERFACESv4=\\"%s\\"/g -i /etc/default/isc-dhcp-server' % self.iface_dut)
        self.expect(self.prompt)
        #self.sendline('sed s/INTERFACESv6=.*/INTERFACESv6=\\"%s\\"/g -i /etc/default/isc-dhcp-server' % self.iface_dut)
        self.sendline('sed "/INTERFACESv6/d" -i /etc/default/isc-dhcp-server')
        self.expect(self.prompt)
        # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
        self.sendline('sysctl -w net.ipv6.conf.%s.accept_dad=0' % self.iface_dut)
        self.expect(self.prompt)
        if not self.wan_no_eth0:
            self.sendline('ifconfig %s %s' % (self.iface_dut, self.gw))
            self.expect(self.prompt)
        #self.sendline('ifconfig %s inet6 add 2001:ed8:77b5:3::101/64' % self.iface_dut)
        #self.expect(self.prompt)
        # TODO: specify these via config
        for nw in [self.cm_network, self.mta_network, self.open_network]:
            self.sendline('ip route add %s via %s' % (nw, self.prov_gateway))
            self.expect(self.prompt)
        # TODO: iface_dut needs an ipv6 addr
        # sysctl net.ipv6.conf.%s.disable_ipv6=0 % iface_dut
        #self.sendline('ip -6 route add 2001:ed8:77b5:2000::/64 via 2001:ed8:77b5:3::222 dev %s metric 1024' % self.iface_dut)
        #self.expect(self.prompt)
        #self.sendline('ip -6 route add 2001:ed8:77b5:2001::/64 via 2001:ed8:77b5:3::222 dev %s metric 1024' % self.iface_dut)
        #self.expect(self.prompt)
        self.update_cmts_isc_dhcp_config(board_config)
        self.sendline('cat /etc/dhcp/dhcpd.conf')
        self.expect(self.prompt)
        self.sendline('(flock -x 9; /etc/init.d/isc-dhcp-server restart; flock -u 9) 9>/etc/init.d/isc-dhcp-server.lock')
        # We expect both, so we need debian 9 or greater for this device
        self.expect('Starting ISC DHCPv4 server: dhcpd.\r\n')
        #self.expect('Starting ISC DHCPv6 server: dhcpd6.\r\n')
        self.expect(self.prompt)
        self.sendline('rm /etc/init.d/isc-dhcp-server.lock')
        self.expect(self.prompt)

        # only start tftp server if we are a full blown wan+provisioner
        if self.wan_cmts_provisioner:
            self.start_tftp_server()

        # errr, this should not need to call into board object
        try:
            from devices import board
            board.update_cfg_for_site()
        except:
            pass

        self.copy_cmts_provisioning_files(board_config)

        self.sendline("sed 's/disable\\t\\t= yes/disable\\t\\t= no/g' -i /etc/xinetd.d/time")
        self.expect(self.prompt)
        self.sendline("grep -q flags.*=.*IPv6 /etc/xinetd.d/time || sed '/wait.*=/a\\\\tflags\\t\\t= IPv6' -i /etc/xinetd.d/time")
        self.expect(self.prompt)
        self.sendline('/etc/init.d/xinetd restart')
        self.expect('Starting internet superserver: xinetd.')
        self.expect(self.prompt)

    def reprovision_board(self, board_config):
        '''New DHCP, cfg files etc for board after it's been provisioned once'''
        self.copy_cmts_provisioning_files(board_config)
        self.update_cmts_isc_dhcp_config(board_config)
        self.sendline('(flock -x 9; /etc/init.d/isc-dhcp-server restart; flock -u 9) 9>/etc/init.d/isc-dhcp-server.lock')
        self.expect(['Starting ISC DHCP(v4)? server.*dhcpd.', 'Starting isc-dhcp-server.*'])
        self.expect(self.prompt)
        self.sendline('rm /etc/init.d/isc-dhcp-server.lock')
        self.expect(self.prompt)

    def get_attr_from_dhcp(self, attr, exp_pattern, dev, station, match_group=4):
        '''Try getting an attribute from the dhcpd.conf.<station> file'''
        val = None
        try:
            self.sendline('cat  /etc/dhcp/dhcpd.conf.%s' % station)
            idx = self.expect(['(%s-%s\s\{([^}]+)(%s\s(%s))\;)' % (dev, station, attr, exp_pattern) ] + ['No such file or directory'] + [pexpect.TIMEOUT], timeout=10)
            if idx == 0:
                # the value should be in group 4
                val = self.match.group(match_group)
        except:
            pass
        return val

    def get_cfgs(self, board_config):
        '''Tries to get the cfg out of the dhcpd.conf for the station in question'''
        try:
            mta_cfg = self.get_attr_from_dhcp('filename', '".*?"', 'mta', board_config['station'])
            mta_cfg_srv = self.get_attr_from_dhcp('next-server', ValidIpv4AddressRegex, 'mta', board_config['station'])

            cm_cfg = self.get_attr_from_dhcp('filename', '".*?"', 'cm', board_config['station'])
            cm_cfg_srv = self.get_attr_from_dhcp('next-server', ValidIpv4AddressRegex, 'cm', board_config['station'])
            if mta_cfg is None or mta_cfg_srv  is None or cm_cfg is None or cm_cfg_srv is None:
                raise
            return [[mta_cfg.replace('"', ''), mta_cfg_srv], [cm_cfg.replace('"',''), cm_cfg_srv]]
        except:
            pass

        return None

    def get_conf_file_from_tftp(self, _tmpdir, board_config):
        '''Retrieve the files in the cfg_list from the tftp sever, puts them in localhost:/tmp/'''

        cfg_list = self.get_cfgs(board_config)
        if cfg_list is None:
            return False

        for elem in cfg_list:
            conf_file = self.tftp_dir+'/'+elem[0]
            server = elem[1]

            # this is where the current (to be downloaded from the tftp)
            # config is going to be placed
            dest_fname = _tmpdir+'/'+os.path.basename(conf_file)+"."+board_config['station']+".current"
            try:
                os.remove(dest_fname)
            except:
                pass

            try:
                print 'Downloading '+server+':'+conf_file+' to '+dest_fname
                from devices.common import scp_from
                scp_from(conf_file, server, self.tftp_device.username, self.tftp_device.password, self.tftp_device.port, dest_fname)

                if not os.path.isfile(dest_fname):
                    # Something has gone wrong as the tftp client has not thrown an
                    # exception, but the file is not where it should be!!
                    print("Tftp completed but %s not found in destination dir: "% dest_fname)
                    return False
                print "Downloaded: "+conf_file
            except:
                print("Failed to download %s from %s"% (conf_file, self.ipaddr))
                return False

        return True

