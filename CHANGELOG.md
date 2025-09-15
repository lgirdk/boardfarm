## 1.0.0 (2025-09-15)

### BREAKING CHANGE

- BOARDFARM-5242
- BOARDFARM-5242
- BOARDFARM-5010
- BOARDFARM-5021
- BOARDFARM-5021
- BOARDFARM-4996
- BOARDFARM-2692
- BOARDFARM-2018
- BOARDFARM-1610
- BOARDFARM-5485
- BOARDFARM-2784

### Feat

- **resources**: add rdkb deploy files
- add pysnmp-lextudio for pdu management
- inventory for RPi4 RDKB
- expose axiros rest to plugin
- add axiros acs class
- add local serial connection
- expose rpi class to plugins
- add PDU management classes
- add rpi rdkb class
- **boardfarm3/templates/**: add template
- **boardfarm3/devices/base_devices/linux_device.py**: add method
- **boardfarm3/devices/linux_lan.py**: added method to handle arp table
- **network_utils.py**: method to generate uuid
- add documentation and readme
- deploy prplos for visual reg demo
- add gui_html_report.css
- prplos gui tests
- add compare png images fucntion
- update flake8/ruff settings
- **linux_lan.py,lan.py**: clear arp cache
- **use_cases/cpe**: implementation
- **usecases/dhcp**: implementation
- **usecases/devices**: getters and utilities
- **cpe**: cpe interfaces enum
- **dataclass**: load or store use-case data
- **templates**: add AFTR and LTS
- **cpe_sw**: Add mising APIs
- **boardfarm3/**: methods to update hosts
- **lib/connections/connect_and_run.py**: add connect and run feature
- **linux_device.py**: setup static routes based on inventory
- add boardfarm_parse_config plugin
- **wlan.py**: method to read packets
- save the logs to a choosen location
- **linux_wlan.py,wlan.py**: add methods to enable and disable monitor mode
- **boardfarm3/**: added flood method
- add delete default route
- update the loc resources hookspecs
- **wlan.py,-networking.py**: add ping support for wlan devices
- **softphone.py**: add devices class and template for softphone
- **kamailio.py**: adding kamailio sipserver device class and template
- **lan.py:wan.py**: port use case helpers
- **linux_device.py:lan.py**: added method
- **prplos_cpe**: add property for tr069 cpe id
- **devices**: add a WAN, LAN, ACS, DHCP and WLAN
- **prplos_cpe**: add device class
- **templates**: cpe and core router
- **connections**: support for local shell command
- **linux_device**: parse device suboptions
- **templates/lan.py**: added template
- **IptablesFirewall**: add get_ip6tables_policy() method
- **linux_device.py**: provide implementation for set_default_gw() and set_static_ip()
- **lan,wan,wlan templates; linux_device**: add stop_traffic() method and implementation
- **lan,wan**: add options for curl
- **boardfarm3/**: added property and templates
- **templates/LAN|WAN**: add send_mldv2_report() method to CPE clients
- **lan|wan|wlan**: add set_date to templates
- **core**: ignore devices option
- **boardfarm3/**: added property and fixed method
- **boardfarm3/**: added templates and fixed methods
- **networking**: adding the usecases
- **base_devices/linux_device.py**: add _get_nw_interface_ipv4_address_async
- **base_devices/linux_device.py**: add async versions of methods needed for hooks
- **plugins/setup_environment.py**: introduce boardfarm_attached_device_configure_async hook
- **boardfarm3/**: make boardfarm_setup_env async
- add boardfarm_attached_device_boot_async hook
- **boardfarm/**: async skip boot flow
- **lib/connections**: add plain telnet connectivity and ser2net inherits from telnet
- **boardfarm3**: add internet_access_cmd parameter
- **templates/lan.py,wan.py,wlan.py**: add abstract method
- **boardfarm3/templates/lan.py,wan.py,wlan.py**: add abstract methods to start iperf traffic on sender and receiver
- **base_devices/linux_device.py**: add function to delete files in the device
- **templates/acs.py,-lan.py,wan.py,wlan.py**: add abstract method to perform scp from linux devices
- update noxfile to python 3.11
- **templates/acs.py,lan.py,wan.py,wlan.py**: add abstract method to delete file from device
- **base_devices/linux_device.py**: add method to perform scp from linux devices
- **base_devices/linux_device.py**: add method to toggle interface up/down
- **templates/lan.py,wan.py,wlan.py**: add abstract method to toggle interface
- **boardfarm3/devices/base_devices/linux_device.py**: add method to start the iperf traffic on sender and receiver
- **lib/networking.py,-lib/parsers/iptables_parser.py**: add method to return the iptables policy
- **templates**: add route methods to wan
- **pyproject.toml**: register no reservation plugin on startup
- **templates/wan.py**: add abstract method to get interface mtu size
- **templates/lan.py**: add abstract method to get interface mtu size
- **templates/wlan.py**: add abstract method to get interface mtu size
- **plugins/no_reservation.py**: add a plugin to enable boardfarm without reservation
- **lib/SNMPv2.py**: implementation of SNMP bulk get method
- introduce docker compose yml generator based on device json templates for docker factory payload
- **boardfarm3/plugins/devices.py**: add skip-boot hook spec and hook flow in boarfarm v3 devices
- **templates/lan.py**: add abstract methods for add and delete upnp rule
- **base_devices/linux_device.py**: add method to return the subnet mask of the interface
- **boardfarm3/templates/tftp.py**: add restart_lighttpd_and_serve_image and stop_lighttpd methods to tftp device template
- **boardfarm3/devices/linux_tftp.py**: add implementation for set_static_ip, restart_lighttpd and stop_lighttpd methods
- **templates/wan.py,-templates/wlan.py**: update the teamplate of WAN and WLAN with get_interface_macaddr method
- **boardfarm3/templates/wlan.py**: add enable/disable ipv6 abstract methods to wlan template
- **boardfarm3/templates/lan.py**: add enable/disable ipv6 abstract methods to lan template
- **boardfarm3/lib/boardfarm_config.py**: make _get_json function public
- **templates/wan.py,-devices/linux_wan.py**: add abstract methods and implementations for rSSH features
- **boardfarm3/lib/utils.py**: add method to get the device ipaddress from the device config options entry
- **templates/acs.py**: update acs template with provision_cpe_via_tr069 method
- **templates/acs.py**: update acs template with provision_cpe_via_tr069 method
- **devices/linux_wan.py,-templates/wan.py**: add abstract methods and return statements for rssh username and password
- **lib/boardfarm_config.py,main.py**: support lockable resources with multiple boards
- **multicast_device.py,templates**: add multicast base device and update templates with multicast methods
- **linux_device**: configure dante proxy
- **lib:boardfarm_config.py**: remove wifi devices with incorrect config
- **lib/interactive_shell.py**: option to add custom marker in the console logs
- **lib/interactive_shell.py**: add option to run boardfarm tests from interactive shell
- fetch jsons from a url
- **main.py,hookspecs/core.py**: add support for lockable resources
- **base_devices:linux_device.py**: add method for nmap
- **connections,boardfarm_pexpect.py**: save console logs to disk
- **tfpt**: tftpd initialisation
- add ser2net driver
- **devices:linux_wlan.py**: port wifi device class to boardfarmV3
- **devices.linux_wan.py**: add contingency check for acs servers reachability request in wan
- **devices,plugins**: add contingency checks for boardfarm devices
- add python_executor
- add voice related exception
- **lib.wrappers.py**: add singleton decorator
- **templates.acs**: add missing methods and update existing methods in acs template
- **lib.networking,templates.wan**: add is_link_up method to wan
- add is_link_up to WAN
- add retry_on_exception
- add faultcode to tr069 exception
- add is_link_up
- **lib/utils.py**: port retry function from boardfarm v2
- **linux_lan.py,lan.py**: add method to set static ip and set default gateway
- **lib,templates,linux_device.py**: add dns_lookup and http_get methods required by use-cases
- **SNMPv2.py**: add snmp v2 library
- **LinuxTFTP**: set ip on startup
- **networking.py,parsers**: add linux networking components
- **exceptions**: add NotSupportedError exception
- **templates,use_cases,devices**: add start http service use cases and buf fixes
- add LinuxLAN, LinuxWAN, AxirosACS implementations
- linux_device uses properties for user and passwd
- **noxfile.py,tox.ini**: test boardfarm on multiple python environments
- uses interact with ptpython
- linux_device has default user and passwd
- preparing master to port boardfarm3
- **boardfarm/lib/env_helper.py**: add support for image_uri
- **deploy-boardfarm-nodes**: fix default route
- **deploy-boardfarm-nodes**: add docker env
- **env_helper.py**: add latest version 2.45 of env schema
- **boardfarm/**: aftr device class impl
- **boardfarm/**: aftr device class impl
- **use_cases/voice.py**: add stop_and_start_sip_server
- **base_devices/board_templates.py**: added template for sw class
- **use_cases/voice.py**: add get_sip_expiry_time usecase
- **devices/kamailio.py**: add get_sipserver_expire_timer implementation
- **lib/common.py**: add install logic
- **devices/linux.py**: add method to get secondary IPv4 address
- **dns**: add support for external DNS servers
- **env_helper**: add support for latest schema
- make code base python3.11 compatible and fix pylint issues
- **pyproject.toml**: lock selenium verison 4.15.0
- **use_cases/networking.py**: add Use Case to get the iptables policy
- **devices/debian_fxs.py**: add method to perform unconditional call forwarding
- **devices/softphone.py**: add method to perform unconditional call forwarding
- **use_cases/voice.py**: add Use Case to enable/disable unconditional call forwarding
- **devices/linux.py**: add method to return interface mtu size
- **use_cases/networking.py**: add param to decide on the iperf destination ip addr
- **use_cases/snmp.py**: add Use Case to perform SNMP bulk get
- **lib/SNMPv2.py**: implementation of SNMP bulk get method
- **use_cases/networking.py**: add Param for the test case to pass destination port for initiating the ipv4 traffic
- **use_cases/networking.py**: add Param for the test case to pass destination port for initiating the ipv6 traffic
- **boardfarm/use_cases/networking.py**: add use case to disable ipv6 on lan/wlan
- **boardfarm/use_cases/networking.py**: add use case to enable ipv6 on lan/wlan
- **use_cases/wifi.py**: add Use Cases to list all ssid / check particular ssid in WLAN
- allow acs seep session to use a certificate
- **ubuntu_asterisk**: make changes to the dockerfile
- add tg2492lg to env check
- **dockerfiles/resources/**: add changes to ubuntu asterisk
- **env_helper.py**: increase version numbers
- increase env number
- **booting.py**: add voice specific changes
- **voice.py**: add pcap verification changes to the lib
- **voice.py**: modify parse pcap to support ipv6 check
- **linux.py**: add bandwidth to the start traffic function
- **ubuntu_asterisk**: add updated sip conf
- **env_helper.py**: add support to latest env version
- **use_cases**: parse ipv6 mldv2 packets
- **debian_lan**: add multicast support
- **pyproject.toml**: update selenium version
- **frr**: added smcroute
- **use_cases:networking.py**: add usecase to perform ping from a device
- **debian_lan**: add multicast scapy support
- **frr**: moving from quagga to frr
- **use_cases:networking.py**: add set_dut_date for board sw
- **use_cases:networking.py**: add use cases for nmap
- **booting.py**: change config voice according to latest sipserver change
- **use_cases/networking.py**: add iptables use_cases
- **softphone.py**: add nameserver entry
- **voice.py**: add voice usecases
- **ubuntu_asterisk**: add freepbx config
- **influx**: add support for capturing cpu & memory utilization in influx db
- **debian_ntp**: add debian ntp docker image
- **linux.py**: add method get_memory_utilization
- **DeviceManager.py**: add samknows device to device manager
- **debian_lan**: add ftp in debian_lan and vsftp in debian_wan
- **use_cases/descriptors.py**: return ipv6 addr
- **booting.py**: add voice specify boot functions
- **use_cases/descriptors.py**: add provisioner descriptor
- **multicast**: ssm multicast libraries
- **asterisk**: dockerfile
- **quagga**: modify implementation to ubuntu
- **base_devices:board_templates.py**: add method is_link_up to BoardSWTemplate class
- **installers.py**: add force parameter to install_vsftpd
- **sip_template.py**: add endpoints specific functions
- add check for multicast server count
- **devices:linux.py,-use_cases:networking.py**: add device class implementation and usecases of the IPerfTrafficGenerator

### Fix

- **rdk_inventory**: fix SSH ports
- linting errors
- **boardfarm/**: add start and stop tcpdump to devices
- **networking**: correct parse http result
- **boardfarm_config**: retaining debian logic
- linting issues
- **aftr.py**: change use case signature
- **pre-commit**: stick to flynt v1.0.3
- **boardfarm3**: add modify templates based on usecases
- **wlan**: to get ip6 addr for wlan1
- **boardfarm3/lib/wrappers.py**: correct return type for callable
- modify pre-commit to ignore tabs for makefile
- **boardfarm3/devices/kea_provisioner.py**: update options with dhcp_options
- make sure the http service is running
- update configs/kea_eth_provisioner lease db
- **linux_lan**: wait 3s before starting danted
- **bf-config**: update the sip server type
- **boardfarm/.pylintrc**: pylint py version change to 3.11
- linting issues
- **connect_and_run**: increase retries
- **connect_and_run**: increase timeout
- **pjsip_phone**: fixing docstring
- **boardfarm3/**: iperf with udp only
- **boardfarm3/**: add method
- **connect_and_run**: add retries
- **base_devices/linux_device.py**: add logic to handle async kill
- **boardfarm3/devices/base_devices/linux_device.py**: fix method get_interface_mask to use correct regex
- **boardfarm3/devices/linux_lan.p**: fix for lan_gateway
- **boardfarm3/templates/wan.py**: add property
- **base_devices/linux_device.py:templates**: add cport functionality
- **boardfarm3/**: modfiy the template and function
- **boardfarm3/lib/networking.py**: fix mypy error
- **linux_devices**: add static routes from inventory for linux devices
- **linux_tftp**: delete any previous default route
- mypy linting issue
- **boardfarm3/devices/linux_lan.py,boardfarm3/templates/lan.py**: fix the create_upnp_rule function
- **wlan.py**: added rel renew methods support
- **boardfarm3/lib/network_utils.py**: add dest to tftp transfer
- **boardfarm3/**: leverage timeout param
- **lib/network_utils.py**: add tftp utility
- **templates/acs.py:genie_acs.py**: add url property
- **sip_server.py**: methods for copying file
- **boardfarm3/**: added params, fixed logic
- **noxfile.py**: pin nox pylint==3.2.6
- **toml**: pin pyasn1=0.6.0
- **core.py**: change name of kamailio to sipcenter_kamailio
- **linux_device.py:lan.py**: support for ipv6
- **linux_device.py**: sync for prompt
- **linux_device.py**: condition if server didn't start
- **linux_device.py**: property name to clear from cache
- **boardfarm3/**: fix for local cmd param
- **prplos_cpe**: fix the cpe_id property
- **hookspec**: add the missing async hook definitions
- **config**: update to a generic openwrt board
- **boardfarm3/**: method to get iperf logs
- **boardfarm3/**: added additional argument
- **boardfarm_config.py**: add station name attr
- **provisioner.py:typing/dhcp.py**: custom type hints
- **provisioner.py**: added base provisioner class
- **boardfarm3/devices/base_devices/**: add scp to local
- allow got linting to pass
- **lan|wan|wlan**: add get_date() to templates
- **boardfarm3/**: fixed dns_lookup method
- **linux_tftp**: add a route for the static ip
- **utils**: initialize webdriver on interact
- **connections**: update LDAP authentication
- **plugins**: add async spec for server_configure
- **devices/base_devices/linux_device.py**: removed firewall utility obj
- add ssh-rsa to key algorithms
- **ser2net**: update regex on connection
- allow a cpe to connect via ser2net
- **networking**: update the http parsing rules
- **networking**: update type hints to comply with ruff
- update login_to_server with default parameter
- **base_devices/linux_device.py**: add await keyword
- **core.py**: boardfarm_post_setup_env does not require boardfarm config
- update noxfile and add pylint plugin to dev dependency
- **lib/**: fix mypy issues
- update perform_scp to match templates
- **boardfarm3/devices/base_devices/linux_device.py**: define linux style prompts in one place
- **lib/device_manager.py**: fix crash when registering a device with property that raises an exception
- **boardfarm3/plugins/core.py**: fix different pytest beaviour on incorrect command line parameter from boardfarm3
- **boardfarm3/lib/SNMPv2.py**: do not modify the snmp set value if the set value is a hex string
- **boardfarm3/plugins/devices.py**: move linux wan device class to boardfarm-lgi-shared
- **boardfarm3/devices/base_devices/linux_device.py**: remove trailing stray characters from ping output
- **boardfarm3/lib/boardfarm_config.py**: fix typo in get_inventory_config function name
- pass path to pexpect.spawn
- **devices/base_devices/linux_device.py**: remove sudo from tcpdump and tshark commands
- **lib/boardfarm_pexpect.py**: fix the double prompt issue in freepbx
- **linux_device**: use sendline for dante cfg
- **lib/SNMPv2.py**: fixed snmp parse regex
- **lib/networking.py**: fix scp failure
- **linux_device**: use sudo_sendline in tcpdump
- **lib/boardfarm_config.py**: disable jsonmerge debug logs
- **templates/acs.py**: revert deletion of the ScheduleInform acs method
- **lib/networking.py**: fix scp failure when the host ip is a ipv6 address
- **.pylintrc**: update .pylintrc file to fix warnings
- crash when using telnet on console
- **lib/interactive_shell.py,main.py**: updated interactive shell look
- **linux_device**: static route is now set
- **lib.boardfarm_config.py**: use locations key to get shared config
- **utils.py**: fix type hinting and code of retry methods
- **linux_tftp.py**: update docstring and fix static ip logic
- stop autocomp running propeties
- terminal longlines changes
- **pyproject.toml**: fix plugin path
- **axiros_acs.py**: get tr69 cpe-id from board
- allows text wrap on long lines
- linting issues
- **boardfarm/devices/axiros_acs.py**: fix add object
- **boardfarm/lib/env_helper.py**: fix for dhcp_options
- **deploy-boardfarm-nodes.sh**: add ipv6 isolate management
- **lib/env_helper.py**: add the version
- **lib/hooks/contingency_checks.py**: add logic for maxcpe
- **boardfarm/lib/SnmpHelper.py**: add fix
- **debian_isc.py**: support sku with no voice support
- **isc_aftr.py**: restarting aftr process
- **lib/env_helper.py**: add the schema version
- **linux.py**: remove buffer data
- **linux_nw_utility.py:networking.py**: add tftpboot as the folder location
- **pyproject.toml**: change selenium install version
- **booting_utils.py**: fix to enable WiFi 5GHz guest settings
- **isc_aftr**: update DNS entry
- **networking.py:linux_nw_utility.py**: add send file via tftp
- **networking.py**: updated condition
- **linux.py**: remove buffer data
- **env_helper.py**: add 2.44 version
- **toml**: pin pyasn1=0.6.0
- restrict numpy<2.1.0
- **networking.py**: updated logic
- **pyproject.toml**: retsrict the pysnmp version
- **linux.py:networking.py**: get server and client logs
- **hooks/contingency_checks.py**: add dual in rechable check
- **connect**: allow access to a AAA configured dev
- **networking.py**: added additional argument
- **boardfarm/use_cases/voice.py**: correct the voice client fun call
- **use_cases/dhcpv6.py**: fixed dhcpv6 packet parsing for mv3 eth
- **boardfarm/lib/common.py**: change wget to curl
- **lib/env_helper.py**: add the latest schema version
- **boardfarm/lib/booting.py**: add transport and dns pref
- **kamailio.py:use_cases/voice.py**: change get exp timmer name
- **use_cases/networking.py**: fixed resolve_dns use case
- acs retry on wsdl schema
- **use_cases/networking.py**: fix nmap usecase
- **devices/kamailio.py,-use_cases/voice.py**: remove redundant param
- **network_testing.py**: change tcpdump cmd flags
- **quagga_router.py**: update interface
- **use_cases/voice.py**: fix set_sip_expiry_time
- **devices/debian_fxs.py**: fix detect_dialtone
- **pyproject**: update easysnmp dependency
- **boardfarm/use_cases/voice.py**: fix get_sip_expiry_time usecase
- **networking**: fix the HTTP parsing
- **use_cases/networking.py**: update anycpe to boardtemplate
- **lib/booting.py**: update extra configure voice param
- **lib/voice.py**: update logic for sip trace
- **use_cases/networking.py**: add sleep
- **lib/voice.py**: update logic for sip trace
- **wifi_lib/manager.py**: fix the WLAN_options
- **contingency_checks.py**: add none check on mode
- **use_cases/networking.py**: fix Use Case
- **lib/env_helper.py**: fix env mismatch
- **lib/linux_nw_utility.py,-use_cases/networking.py**: fix method
- **boardfarm/lib/common.py**: run firefox as headless when specified
- run tcpdump as root user
- download aftr via mgmt iface
- **networking.py**: added interface param
- **common**: update setting firefox profile
- **lib/firewall_parser.py,-lib/linux_nw_utility.py**: fix to get the iptables policy
- **voice**: fix the console sync issue
- **boardfarm/lib/booting.py**: fix digit map issue
- **boardfarm/devices/axiros_acs.py**: fix xml parser error when non formatted, non printable or non ascii characters present
- kill webfsd on wan setup
- **boardfarm/lib/booting.py**: introduce wait for hw boot after reset in booting class
- **use_cases/networking.py**: fixed nmap method
- **boardfarm/use_cases/networking.py**: update nmap board condition
- **boardfarm/use_cases/networking.py**: fix nmap board condition
- **boardfarm/lib/hooks/contingency_checks.py**: acs contingency check has to be performed based on the provisioning mode
- selenium < 4.10.0
- acs do not verify ssl session
- **softphone.py**: change softphone nameserver order
- **boardfarm/use_cases/voice.py**: change call waiting fn to use dtmf
- **kamailio.py**: add url to sipcenter template
- **multicast**: parse IPv4 igmp type
- **booting.py**: fix the error thrown
- **linux.py**: add ipv6 support for scp
- **multicast**: use cases signature fix
- send dhcp-client-identifier as a string
- flake8 ignore  B028, B017
- **acs.py**: use case to return acs urls
- **softphone**: add nameserver to the top
- **booting.py**: check if board is in dslite for mv3
- **debian_fxs.py,softphone.py,sip_template.py**: fix usage of descriptors in phone class
- **booting**: retry on tr-069 provisioning
- **env_helper**: lan clients number mismatch
- **softphone.py,debian_fxs.py,sip_template.py**: remove allocate number funtion and related
- **hooks:contingency_checks**: update acs dns check in contingency
- change gitlab to github
- retry on acs contingency
- **sip_template.py**: fix softphone initialisation error
- **common.py**: remove passive mode connection from ftp_upload_download
- **linux.py**: simplify regex for validating cpu load in get_load_avg method
- **use_cases/networking.py**: add kwargs
- **lib:hooks:contingency_checks.py**: remove the usage of arm in CC
- **networking.py**: add ipv6 dns resolve
- **use_cases/dhcp.py**: update dhcp methods
- **common.py**: update expect statement of password prompt for ftp_useradd
- **use_cases/dhcpv6.py**: add additional_args param
- **SNMPv2.py**: correct the regex and match
- add timeout to parse_sip_trace usecase

### Refactor

- **boardfarm3/lib/odh**: add odh to boardfarm
- **base_devices/linux_device.py:lan.py:wan.py**: refactor method name hping flood
- move demo pages to gui/prplos
- remove resources/configs resources/dockerfiles
- **core.py,boardfarm_config_example.json**: rename the devices dictionary keys
- **lib/multicast.py**: implement proper type hinting
- align docstring with methods signature
- **networking.py**: fix issues found by ruff 0.2.0
- **docs**: delete empty or old documentation
- **linter**: fix black errors
- **boardfarm_config**: remove nox/flake8 errors
- update compose generator due to changes in schema
- **boardfarm3/templates/wlan.py**: update enable_ipv6 and disable_ipv6 template methods for wlan
- **boardfarm3/templates/lan.py**: update enable_ipv6 and disable_ipv6 template methods for lan
- **templates/wan.py**: refactor the method connect_to_board_via_reverse_ssh to return bool
- **lib/SNMPv2.py**: refactor the code that performs snmpset
- **boardfarm3/lib/boardfarm_config.py**: refactoring via ruff
- **devices/linux_wan.py**: modify the command to get the network statistics
- introduce ruff linter
- **scripts/**: remove scripts folder
- **boardfarm3/templates/wan.py,-boardfarm3/devices/linux_wan.py**: modify the signature of rssh_password
- **lib/networking.py**: add fqdn and rework dns class
- **lib/SNMPv2.py**: make get_mib_oid public
- **lib/boardfarm_config.py,pyproject.toml**: use new flexible inventory schema
- **lib/interactive_shell.py,plugins/core.py**: make interactive shell extensible
- **devices:linux_wlan.py**: remove is_wifi_ssid_listed from template
- makes configuration more flexible
- **devices.linux_lan.py**: move linux lan device to lgi-shared since it require cable modem
- move wan options to wan device
- update syntax to py3.9
- remove redundant sendline
- **py.typed**: add py.typed file to indicate the package is type hinted
- rename package from boardfarm to boardfarm3
- **devices,plugins,lib,templates**: boardfarm v3 plugins, libraries, templates and devices
- **devices,lib,use_cases**: cleanup boardfarm repo for v3
- **devices,lib,templates**: Cleanup boardfarm repo for v3
- **env_helper**: add latest env
- **pre-commit-config.yaml**: update isort version
- **axiros_acs.py,acs_template.py**: update AcsTemplate and update AxirosACS

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

- Do not merge until all the executors have been updated!
BOARDFARM-1698
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
