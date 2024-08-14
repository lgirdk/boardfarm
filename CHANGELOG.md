## 2024.33.0 (2024-08-14)

### Fix

- **networking.py**: updated logic

## 2024.31.0 (2024-08-01)

## 2024.29.0 (2024-07-18)

### Fix

- **pyproject.toml**: retsrict the pysnmp version
- **linux.py:networking.py**: get server and client logs
- **hooks/contingency_checks.py**: add dual in rechable check
- **connect**: allow access to a AAA configured dev
- **networking.py**: added additional argument
- **boardfarm/use_cases/voice.py**: correct the voice client fun call
- **use_cases/dhcpv6.py**: fixed dhcpv6 packet parsing for mv3 eth

## 2024.27.0 (2024-07-03)

### Fix

- **boardfarm/lib/common.py**: change wget to curl

## 2024.25.0 (2024-06-20)

### Fix

- **lib/env_helper.py**: add the latest schema version
- **boardfarm/lib/booting.py**: add transport and dns pref

## 2024.23.0 (2024-06-05)

### Fix

- **kamailio.py:use_cases/voice.py**: change get exp timmer name

## 2024.22.0 (2024-05-27)

### Refactor

- **env_helper**: add latest env

## 2024.20.0 (2024-05-14)

### Fix

- **use_cases/networking.py**: fixed resolve_dns use case
- acs retry on wsdl schema

## 2024.17.0 (2024-04-26)

### Fix

- **use_cases/networking.py**: fix nmap usecase

## 2024.16.0 (2024-04-15)

## 2024.13.0 (2024-03-27)

### Fix

- **devices/kamailio.py,-use_cases/voice.py**: remove redundant param

## 2024.11.0 (2024-03-14)

### Feat

- **use_cases/voice.py**: add stop_and_start_sip_server

### Fix

- **network_testing.py**: change tcpdump cmd flags
- **quagga_router.py**: update interface
- **use_cases/voice.py**: fix set_sip_expiry_time
- **devices/debian_fxs.py**: fix detect_dialtone
- **pyproject**: update easysnmp dependency
- **boardfarm/use_cases/voice.py**: fix get_sip_expiry_time usecase

## 2024.09.0 (2024-02-28)

### Fix

- **networking**: fix the HTTP parsing

## 2024.07.0 (2024-02-15)

### Feat

- **base_devices/board_templates.py**: added template for sw class

### Fix

- **use_cases/networking.py**: update anycpe to boardtemplate
- **lib/booting.py**: update extra configure voice param

## 2024.05.0 (2024-02-01)

### Feat

- **use_cases/voice.py**: add get_sip_expiry_time usecase
- **devices/kamailio.py**: add get_sipserver_expire_timer implementation

### Fix

- **lib/voice.py**: update logic for sip trace
- **use_cases/networking.py**: add sleep
- **lib/voice.py**: update logic for sip trace

## 2024.04.0 (2024-01-22)

### Feat

- **lib/common.py**: add install logic
- **devices/linux.py**: add method to get secondary IPv4 address
- **dns**: add support for external DNS servers
- **env_helper**: add support for latest schema

### Fix

- **wifi_lib/manager.py**: fix the WLAN_options
- **contingency_checks.py**: add none check on mode
- **use_cases/networking.py**: fix Use Case

## 2023.50.0 (2023-12-12)

### Feat

- make code base python3.11 compatible and fix pylint issues
- **pyproject.toml**: lock selenium verison 4.15.0

### Fix

- **lib/env_helper.py**: fix env mismatch
- **lib/linux_nw_utility.py,-use_cases/networking.py**: fix method
- **boardfarm/lib/common.py**: run firefox as headless when specified
- run tcpdump as root user

## 2023.45.0 (2023-11-08)

### Fix

- download aftr via mgmt iface
- **networking.py**: added interface param
- **common**: update setting firefox profile

## 2023.43.0 (2023-10-24)

### Feat

- **use_cases/networking.py**: add Use Case to get the iptables policy
- **devices/debian_fxs.py**: add method to perform unconditional call forwarding
- **devices/softphone.py**: add method to perform unconditional call forwarding
- **use_cases/voice.py**: add Use Case to enable/disable unconditional call forwarding

### Fix

- **lib/firewall_parser.py,-lib/linux_nw_utility.py**: fix to get the iptables policy

## 2023.42.0 (2023-10-16)

### Feat

- **devices/linux.py**: add method to return interface mtu size

## 2023.39.0 (2023-09-29)

### Feat

- **use_cases/networking.py**: add param to decide on the iperf destination ip addr

### Fix

- **voice**: fix the console sync issue
- **boardfarm/lib/booting.py**: fix digit map issue

## 2023.37.0 (2023-09-13)

### Feat

- **use_cases/snmp.py**: add Use Case to perform SNMP bulk get
- **lib/SNMPv2.py**: implementation of SNMP bulk get method
- **use_cases/networking.py**: add Param for the test case to pass destination port for initiating the ipv4 traffic
- **use_cases/networking.py**: add Param for the test case to pass destination port for initiating the ipv6 traffic

### Fix

- **boardfarm/devices/axiros_acs.py**: fix xml parser error when non formatted, non printable or non ascii characters present

## 2023.36.0 (2023-09-04)

### Fix

- kill webfsd on wan setup

## 2023.33.0 (2023-08-18)

### Fix

- **boardfarm/lib/booting.py**: introduce wait for hw boot after reset in booting class

## 2023.29.0 (2023-07-20)

### Feat

- **boardfarm/use_cases/networking.py**: add use case to disable ipv6 on lan/wlan
- **boardfarm/use_cases/networking.py**: add use case to enable ipv6 on lan/wlan
- **use_cases/wifi.py**: add Use Cases to list all ssid / check particular ssid in WLAN

### Fix

- **use_cases/networking.py**: fixed nmap method
- **boardfarm/use_cases/networking.py**: update nmap board condition

## 2023.27.0 (2023-07-05)

### Feat

- allow acs seep session to use a certificate

### Fix

- **boardfarm/use_cases/networking.py**: fix nmap board condition

## 2023.25.0 (2023-06-23)

### Fix

- **boardfarm/lib/hooks/contingency_checks.py**: acs contingency check has to be performed based on the provisioning mode
- selenium < 4.10.0

## 2023.23.0 (2023-06-07)

### Feat

- **ubuntu_asterisk**: make changes to the dockerfile

### Fix

- acs do not verify ssl session

## 2023.21.0 (2023-05-24)

### Feat

- add tg2492lg to env check

## 2023.17.0 (2023-04-26)

### Fix

- **softphone.py**: change softphone nameserver order

## 2023.16.0 (2023-04-17)

### Feat

- **dockerfiles/resources/**: add changes to ubuntu asterisk

## 2023.13.0 (2023-03-30)

### Fix

- **boardfarm/use_cases/voice.py**: change call waiting fn to use dtmf
- **kamailio.py**: add url to sipcenter template

## 2023.11.0 (2023-03-15)

### Fix

- **multicast**: parse IPv4 igmp type

## 2023.09.0 (2023-03-02)

### Feat

- **env_helper.py**: increase version numbers
- increase env number
- **booting.py**: add voice specific changes
- **voice.py**: add pcap verification changes to the lib

### Fix

- **booting.py**: fix the error thrown

## 2023.08.0 (2023-02-20)

### Feat

- **voice.py**: modify parse pcap to support ipv6 check
- **linux.py**: add bandwidth to the start traffic function

### Fix

- **linux.py**: add ipv6 support for scp

## 2023.05.0 (2023-02-03)

### Feat

- **ubuntu_asterisk**: add updated sip conf
- **env_helper.py**: add support to latest env version
- **use_cases**: parse ipv6 mldv2 packets
- **debian_lan**: add multicast support

### Fix

- **multicast**: use cases signature fix
- send dhcp-client-identifier as a string

### Refactor

- **pre-commit-config.yaml**: update isort version

## 2023.03.0 (2023-01-18)

### BREAKING CHANGE

- BOARDFARM-2784

### Feat

- **pyproject.toml**: update selenium version
- **frr**: added smcroute
- **use_cases:networking.py**: add usecase to perform ping from a device
- **debian_lan**: add multicast scapy support
- **frr**: moving from quagga to frr
- **use_cases:networking.py**: add set_dut_date for board sw

### Fix

- flake8 ignore  B028, B017
- **acs.py**: use case to return acs urls
- **softphone**: add nameserver to the top

## 2022.51.0 (2022-12-21)

### Feat

- **use_cases:networking.py**: add use cases for nmap
- **booting.py**: change config voice according to latest sipserver change

### Fix

- **booting.py**: check if board is in dslite for mv3
- **debian_fxs.py,softphone.py,sip_template.py**: fix usage of descriptors in phone class

## 2022.49.0 (2022-12-07)

### Feat

- **use_cases/networking.py**: add iptables use_cases
- **softphone.py**: add nameserver entry

### Fix

- **booting**: retry on tr-069 provisioning
- **env_helper**: lan clients number mismatch
- **softphone.py,debian_fxs.py,sip_template.py**: remove allocate number funtion and related
- **hooks:contingency_checks**: update acs dns check in contingency

## 2022.47.0 (2022-11-23)

### Feat

- **voice.py**: add voice usecases
- **ubuntu_asterisk**: add freepbx config

 ### Fix

- change gitlab to github
- retry on acs contingency
- **sip_template.py**: fix softphone initialisation error

## 2022.45.0 (2022-11-09)

### Feat

- **influx**: add support for capturing cpu & memory utilization in influx db
- **debian_ntp**: add debian ntp docker image
- **linux.py**: add method get_memory_utilization

### Fix

- **common.py**: remove passive mode connection from ftp_upload_download
- **linux.py**: simplify regex for validating cpu load in get_load_avg method
- **use_cases/networking.py**: add kwargs

## 2022.43.0 (2022-10-28)

### Feat

- **DeviceManager.py**: add samknows device to device manager

### Fix

- **lib:hooks:contingency_checks.py**: remove the usage of arm in CC

## 2022.41.0 (2022-10-12)

### Feat

- **debian_lan**: add ftp in debian_lan and vsftp in debian_wan
- **use_cases/descriptors.py**: return ipv6 addr
- **booting.py**: add voice specify boot functions
- **use_cases/descriptors.py**: add provisioner descriptor
- **multicast**: ssm multicast libraries
- **asterisk**: dockerfile
- **quagga**: modify implementation to ubuntu

### Fix

- **networking.py**: add ipv6 dns resolve
- **use_cases/dhcp.py**: update dhcp methods

## 2022.39.0 (2022-09-28)

### Feat

- **base_devices:board_templates.py**: add method is_link_up to BoardSWTemplate class
- **installers.py**: add force parameter to install_vsftpd


### Fix

- **common.py**: update expect statement of password prompt for ftp_useradd
- **use_cases/dhcpv6.py**: add additional_args param
- **SNMPv2.py**: correct the regex and match


### Refactor

- **axiros_acs.py,acs_template.py**: update AcsTemplate and update AxirosACS

## 2022.37.0 (2022-09-21)

### Feat

- **sip_template.py**: add endpoints specific functions
- add check for multicast server count
- **devices:linux.py,-use_cases:networking.py**: add device class implementation and usecases of the IPerfTrafficGenerator

### Fix

- add timeout to parse_sip_trace usecase

## 2022.35.0 (2022-08-31)

### Feat

- **dhcpv6.py**: add timeout to parse_dhcpv6_trace usecase
- **booting_utils.py**: add condition to connect wifi
- **env_helper.py**: add support to new env schema

### Fix

- disable check on signature checker
- depends-on change rebase -> checkout
- **networking.py**: update the regex in http_get usecase
- **networking.py**: fix the regex in http_get usecase
- **dhclient-script**: ns count fix
- **debian_lan**: no mgmt dns in dhclient.conf
- **debian_isc**: run v4/v6 config together
- **arguments.py**: change operator
- **axiros_acs.py**: remove pprint
- **axiros_acs.py**: remove pprint from output
- **networking.py**: remove the use of the output from print

### Refactor

- **acs_template**: add bool and int to SPV type hinting

## 2022.33.0 (2022-08-17)

### Feat

- can read the inventory.json from web location
- add tones_dict to sw template
- **DeviceManager.py**: add ssam client to device manager

### Fix

- **debian_lan**: fix dhclient-script issue
- pylint issue == to is
- do not install packages
- **debian_sipcenter**: add bind.so to sipcenter
- **debian**: fix dnsmasq configuration
- **__init__.py**: remove argument model

## 2022.31.0 (2022-08-03)

### Fix

- add mitm as it is needed in scripts
- **contingency_checks.py**: fix contingency check device list
- **debian_dns**: update dnsutils package version
- **networking.py**: modify the use case http_get
- **networking.py**: fix the parse response logic for failure
- **lib:env_helper.py**: update get_board_hardware_type with F5685LGB from env_helper
- **pyproject.toml**: rm jira from dependencies

## 2022.29.0 (2022-07-20)

### Feat

- **kea_dhcp**: allow multiple host reservations

### Fix

- **devices:kamailio.py**: fix the sipserver_user_add function to take the correct password for a sip user

### Refactor

- sonarQ reporting moved to cicd

## 2022.27.0 (2022-07-07)

### Feat

- **platform/debian**: add ptr record suppport
- **DeviceManager**: add enum for olt

### Fix

- flake8 B023 error
- fix wifi board fail at post boot
- invoke power off on board.hw

## 2022.25.0 (2022-06-20)

### Feat

- **bft_pexepct_helper**: add check_output
- **pylint**: bump pylint to 2.14.1

### Fix

- **dhcp.py**: add timeout for parse_dhcp_trace
- dnsmasq not starting when "auth-zone=" in .conf

## 2022.23.0 (2022-06-08)

### Feat

- **devices:base_devices:mib_template.py**: add sw_update_table_mib to the mib template of the BoardSWTemplate
- **env_helper.py**: add get_board_gui_language

### Fix

- **debian_dns**: update apt libraries' version
- **quagga**: allows addition of more interfaces

### Refactor

- **voice.py,-wifi.py**: add voice resources and wifi resources

## 2022.21.0 (2022-05-25)

### Feat

- **kea_provisioner**: add HTTP APIs for DHCP

### Fix

- **devices:base_devices:mib_template.py**: add sw_server_address_mib property to MIBTemplate
- **use_cases:dhcp.py**: fix use-case get_dhcp_suboption_details to fetch suboptions for option 125
- **debian_wan**: add option to set static ipv6 route
- **lib:env_helper.py**: fix failures with provisioner dhcp options

## 2022.19.0 (2022-05-11)

### Feat

- **use_cases:dhcp.py**: implement usecases to configure and trigger dhcpinform packets
- **debian_lan,debian_wan**: add support to add webfs server
- add debian_kea_provisioner dockerfile

### Fix

- **lib:SNMPv2.py**: fix parse_snmp_output for IndexError
- **dockerfiles**: fix missing debian binay packages
- **networking.py**: fix off by one bug related to /32 subnet

### Refactor

- **lib:env_helper.py**: segregate docsis and non-docsis env_helper

## 2022.17.0 (2022-04-28)

### Feat

- add schema 2.22 to env helper
- **linux.py,networking.py**: add support to spin up/down webserver using webfsd
- **booting.py,contingency_checks.py**: add support for static ip assignment for lan/wlan clients
- **lib:hooks:contingency_checks.py**: Contingency Check Functionality Segregation

### Fix

- add mgmt when fetching from server
- **acs_server**: add support for another ACS
- **devices:debian_wan.py**: add ipv6.google.com to resolve as wan container's ip address
- disable acs pcap capture by default

### Refactor

- **pylint-fixes**: fix pylint errors

## 2022.15.0 (2022-04-14)

### BREAKING CHANGE

- MVX_TST-56392
- BOARDFARM-1666

### Feat

- **devices:base_devices:board_templates**: update BoardSWTemplate with nw_utility and firewall instances
- **use_cases:networking.py**: use cases to block and unblock traffic via iptables firewall rule
- **networking.py**: add usecase for dhcp renew
- update template and booting for new board
- add new api to resolve board type
- **dhcp.py**: add DHCP parse Use Cases

### Fix

- remove yamlfmt/yamllint from pre-commit
- bumps the env version
- **pre-commit**: update pre-commit hooks to latest versions and autofix issues

## 2022.13.0 (2022-03-31)

### BREAKING CHANGE

- BOARDFARM-1734

### Feat

- **use_cases:console.py**: implement usecase to restart the erouter interface
- **linux.py,networking.py**: add support to set static ip , ip search in pool
- **contingency_checks.py**: add support to disable lan client init
- **wifi_use_cases**: update access to wifi object getter, change the usage in use cases

### Fix

- **pyproject.toml**: freeze pylint dependency to last working version

### Refactor

- **dockerfiles**: Create dockerfile for each device and cleanup

## 2022.11.0 (2022-03-16)

### Feat

- **devices:board_templates.py,mib_template.py,linux.py**: add mib template to support vendor specific mib configurations for software download
- **networking.py**: add dns_resolve  uc
- **device_getters.py**: add provisioner getter
- **voice.py**: remove sleep from disconnect_the_call
- traffic_gen return TrafficGeneratorResults

### Fix

- **linux.py**: change regular expression to get process id
- **quagga_router.py**: update ip route method to fetch route from quagga instance

### Refactor

- **debian_lan.py**: validate ipv6 address is obtained and throw exception

## 2022.09.0 (2022-03-02)

### BREAKING CHANGE

- BOARDFARM-1500

### Feat

- **debian_isc.py**: add support for invalid dhcp gateway
- add get_load_avg to sw template
- **debian**: fetch DNS entry from inventory json and update in dnsmasq.conf
- **linux.py**: add graceful error handling
- **linux**: add support for ping using json cli
- add 2.19 env version
- **boardfarm:use_cases:networking.py**: write a use case to parse ICMP responses and compare

### Fix

- **voice.py**: reduce sleep time in makecall
- **quagga_router.py**: update atexit call and docstrings

## 2022.07.0 (2022-02-16)

### Feat

- **quagga_router.py**: add quagga router device class
- **linux.py**: add support for tcpdump capture,read[tcpdump,tshark]
- **traffic_generator.py**: formalise traffic generator template
- **debian_lan**: add iw and wpasupplicant packages in image

### Fix

- **pyproject.toml**: freeze pyvirtualdisplay package version to 2.2
- **pyproject.toml**: pin elasticsearch to stay compliant with api
- increase cli size

### Refactor

- **pyproject.toml**: freeze selenium dependency to 4.1.0

## 2022.05.0 (2022-02-02)

### Feat

- **devices:softphone.py,debian_fxs.py**: implement enable_call_waiting and enable_call_forwarding_busy use cases for softphone
- **getters.py**: add getters for lan and wan clients

### Fix

- **lib:voice.py**: fix _parse_rtp_trace usecase to check for rtp packets associated to a SIP setup-frame
- **debian_wan**: replace google.com with wan.boardfarm.com for v4 and v6
- **debian_fxs**: update debian:stable-slim with debian:buster-slim
- **connection_decider**: use strict match for connection type
- **pyproject.toml**: pin dependency for selenium version 3.141.0
- **devices:debian_lan.py**: set icmp_echo_ignore_broadcasts to false on lan devices
- **boardfarm:lib:voice**: fix _parse_rtp_trace when start and end indexes are same

## 2022.03.0 (2022-01-20)

### BREAKING CHANGE

- BOARDFARM-1456

### Feat

- **devices:softphone.py**: implement the unimplemented usecases for softphone
- add connect to DUT via ssh
- **device-manager**: register wifi devices

### Fix

- **devices:softphone.py**: fix softphone pjsip config to disable TCP transport
- **networking.py**: add link_local_ipv6 to IPAddresses dataclass
- **devices:linux.py**: fix get_interface_ipaddr to handle AttributeError and throw PexpectTimeoutError
- **devices:debian_isc.py**: fix for port number of acs url in vendor specific dhcp configuration
- **debian**: updated pkgs that can be installed
- fixes to run with debian:buster-slim image
- **debian**: fix pexpect xterm env set
- **installers**: minor fix on apt_install

## 2022.01.0 (2022-01-05)

### BREAKING CHANGE

- If using Docsis devices the latest Docsis change must be picked.

### Feat

- get image use image_uri
- **multicast**: add multicast usecases
- **quagga**: add mrouted daemon

### Fix

- **boardfarm:resources:configs:kamailio.cfg**: update kamailio.cfg to configure timeout of 25sec
- **boardfarm:devices:debian_isc.py**: fix acs url in vendor specific dhcpoptions to use http as prefix
- **boardfarm:use_cases:voice.py**: handle exception for hangup in shutdown_phone usecase

## 2021.51.0 (2021-12-22)

### Feat

- **quagga-pim**: add IGMP multicast routing for interface
- enable/disable acs pcap capture
- improved name discovery

### Fix

- **devices:linux.py**: add fix to fetch erouter0/lan ipv6 on linux console when output is delayed/untidy after command execution
- do not use get_pytest_name yet
- fix test name fetching in acs intercept
- **devices:debian_lan.py**: handle timeout error when tshark read is too long for failed lan renewal

## 2021.49.0 (2021-12-09)

### Feat

- **use_cases:voice.py**: add place_call_offhook use case for voice
- **networking.py**: Add IPAddresses data class for erouter use case at common location
- **use_cases:voice.py**: add off hook use case for voice

### Fix

- **lib:dhcpoption.py**: fix ManufacturerOUI under DHCP Option 125 on LAN side
- **pylint**: Add pylint config and fix pylint issues.

## 2021.47.0 (2021-11-24)

### Fix

- **lib:voice.py**: add 1 second delay to verify RTP packets and handle few exceptions

## 2021.46.0 (2021-11-18)

### Feat

- **pyproject.toml**: Add commitizen-specific config. Prune tbump config.
- **pyproject.toml**: Add tbump config and bump version manually.
- **boardfarm/bft**: Add option to skip resource reservation status check on Jenkins
- **linux.py**: Add hostname property for all linux devices.
- remove zephyr dead code
- **devices:debian_fxs.py,softphone.py**: fix and implement sip abstract methods
- **use_cases:networking.py**: add use_cases to be used by TCs to avoid direct access to board consoles
- **lib:linux_nw_utility.py,linux_console_utility.py**: add network and dut console utilities
- **bft,lockableresources**: Use Jenknins Lockable Resources in Boardfarm to manage modems
- **quagga**: dockerfile for quagga router
- **installers.py**: add method get_interface_private_ip6addr
- **networking.py-wifi.py-wifi_template.py**: add wifi usecases
- **acs**: show console interactions
- **voice**: add voice conference use cases
- **devices-base_devices-board_template**: add FXO as voice
- **devices:-base_devices:-fxo_template**: add new template class to be used by MTA template
- **use_cases/snmp.py**: Add basic generic snmp use cases (wrappers around SNMPv2).
- **platform/debian**: lighttpd and tftpd use the same directory
- Add generic scp command implementation to linux device.

### Fix

- **resources:configs:kamailio.cfg**: configure kamailio to send "181 Call is Being Forwarded" packet on call forward busy
- **debian_fxs**: remove reply with code implementation
- **devices:softphone.py**: hardening of the phone_config and phone_start of softphone device to fix issues
- **lib,use_cases:voice.py**: add new use cases for sipserver/voice rtp, remove the legacy ones and add support for media attribute, connection info check
- **devices:debian_fxs,devices:kamailio**: harden the implementations of fxs and sip server devices
- **devices:debian_isc.py**: provide a different acs url from config file both for v4 and v6 when dhcp vendor options are configured
- **common.py**: split send_to_influx further into validate_influx_connection
- change gui resolution to 1920x1080
- **influx_db_helper.py**: add timeout parameter to influx db connection request
- **lockableresources.py**: Fix wifi enclosure device selection based on board type
- **lib:installers.py**: add recovery solution when acs server console is hung during apt install
- **devices/serialphone.py**: modify the wrapper function exit_python_on_exception
- **use_cases**: fix docstrings to make sphinx happy
- **kamailio.cfg**: modify configurations to use nonce value only once for authentication
- **quagga**: add natting on router
- **lib/common.py**: remove unused self argument from configure_ovpn. Return bool success value
- **installers.py**: add fix for openvpn ipv6 server connection
- **implement-voice-conference-APIs**: derive implementation for Voice conference call signatures
- **devices-base_devices-sip_template**: update signatures
- **env_helper.py**: handle scenarios with list of dictionaries and list of strings in env request validation
- **installers.py**: add print statements instead of debug for lan client IRC scripts
- fix pylint errors
- Do not restart interface twice during CC. Flush tcpdump buffer before kill

### Refactor

- **linux.py**: return dhcp renew output
- **axiros_acs**: fix the interface name
- **axiros_acs**: add acs aux iface name
- change lib to docsis_lib globally
