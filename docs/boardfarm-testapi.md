# Boardfarm Test API Documentation

This document describes the test API that Boardfarm defines for various device types in the testbed. The API is organized by device type, with each device type inheriting from base templates and providing specific implementations.

## Table of Contents

- [Device Types Overview](#device-types-overview)
- [bf_cpe (CPE Device)](#bf_cpe-cpe-device)
- [bf_lan (LAN Device)](#bf_lan-lan-device)
- [bf_wan (WAN Device)](#bf_wan-wan-device)
- [bf_wlan (WLAN Device)](#bf_wlan-wlan-device)
- [bf_acs (ACS Device)](#bf_acs-acs-device)
- [bf_dhcp (Provisioner Device)](#bf_dhcp-provisioner-device)
- [bf_tftp (TFTP Device)](#bf_tftp-tftp-device)
- [bf_kamailio (SIP Server Device)](#bf_kamailio-sip-server-device)
- [bf_phone (SIP Phone Device)](#bf_phone-sip-phone-device)
- [Base Classes](#base-classes)

## Device Types Overview

Boardfarm registers the following device types in `boardfarm3/plugins/core.py`:

- `bf_tftp`: LinuxTFTP
- `bf_lan`: LinuxLAN
- `bf_wan`: LinuxWAN
- `bf_wlan`: LinuxWLAN
- `bf_acs`: GenieACS
- `bf_cpe`: PrplDockerCPE
- `bf_dhcp`: KeaProvisioner
- `bf_kamailio`: SIPcenterKamailio5
- `bf_phone`: PJSIPPhone
- `bf_rpi4rdkb`: RPiRDKBCPE
- `axiros_acs`: AxirosACS
- `vcpe`: VCPE_LXC

## bf_cpe (CPE Device)

The CPE (Customer Premises Equipment) device represents the router/gateway device being tested.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `CPE`
- **Implementation**: `PrplDockerCPE`
- **Components**:
  - `hw`: `CPEHW` (hardware component)
  - `sw`: `CPESW` (software component)

### CPE Properties

#### Device Configuration
- `config` (dict): Device configuration dictionary
- `device_name` (str): Name of the device
- `device_type` (str): Type of the device

#### Hardware Component (`hw`)

**Properties:**
- `config` (dict): Hardware configuration
- `mac_address` (str): CPE MAC address
- `wan_iface` (str): WAN interface name (e.g., "eth1")
- `mta_iface` (str): MTA interface name (for voice)
- `serial_number` (str): CPE serial number

**Methods:**
- `connect_to_consoles(device_name: str)`: Establish connection to device console
- `get_console(console_name: str)`: Return console instance with given name
- `power_cycle()`: Power cycle the CPE via CLI
- `wait_for_hw_boot()`: Wait for CPE to have WAN interface added
- `flash_via_bootloader(image, tftp_devices, termination_sys, method)`: Flash CPE via bootloader
- `disconnect_from_consoles()`: Disconnect/Close console connections
- `get_interactive_consoles()`: Get interactive consoles of the device

#### Software Component (`sw`)

**Properties:**
- `version` (str): CPE software version
- `erouter_iface` (str): E-Router interface name
- `lan_iface` (str): LAN interface name (e.g., "br-lan")
- `guest_iface` (str): Guest network interface name (e.g., "br-guest")
- `json_values` (dict): CPE-specific JSON values (UCI output)
- `gui_password` (str): GUI login password
- `cpe_id` (str): TR069 CPE ID
- `tr69_cpe_id` (str): TR-69 CPE Identifier
- `lan_gateway_ipv4` (IPv4Address): LAN Gateway IPv4 address
- `lan_gateway_ipv6` (IPv6Address): LAN Gateway IPv6 address
- `lan_network_ipv4` (IPv4Network): LAN IPv4 network
- `wifi` (WiFiHal): WiFi component instance
- `dmcli` (DMCLIAPI): Dmcli instance running in CPE Software
- `nw_utility` (NetworkUtility): Network utility component
- `firewall` (IptablesFirewall): Firewall component
- `aftr_iface` (str): AFTR interface name

**Methods:**
- `get_provision_mode()`: Return provision mode (e.g., "dual", "ipv4", "ipv6")
- `is_production()`: Check if production software
- `reset(method: str | None)`: Perform reset via given method
- `factory_reset(method: str | None)`: Perform factory reset CPE
- `wait_for_boot()`: Wait for CPE to boot
- `wait_device_online()`: Wait for WAN interface to come online
- `verify_cpe_is_booting()`: Verify CPE is booting
- `configure_management_server(url, username, password)`: Configure management server URL
- `is_online()`: Check if CPE is online
- `get_seconds_uptime()`: Return uptime in seconds
- `get_interface_ipv4addr(interface: str)`: Return interface IPv4 address
- `get_interface_ipv6addr(interface: str)`: Return interface IPv6 address
- `get_interface_link_local_ipv6_addr(interface: str)`: Return link local IPv6 address
- `is_link_up(interface: str, pattern: str)`: Return link status
- `get_interface_mac_addr(interface: str)`: Return interface MAC address
- `is_tr069_connected()`: Check if TR-69 agent is connected
- `get_load_avg()`: Return current load average
- `get_memory_utilization()`: Return current memory utilization
- `enable_logs(component: str, flag: str)`: Enable logs for given component
- `get_board_logs(timeout: int)`: Return board console logs
- `read_event_logs()`: Return event logs from logread command
- `get_running_processes(ps_options: str)`: Return currently running processes
- `get_ntp_sync_status()`: Get NTP synchronization status
- `kill_process_immediately(pid: int)`: Kill process by PID
- `get_boottime_log()`: Return boot time log
- `get_tr069_log()`: Return TR-069 log
- `get_file_content(fname: str, timeout: int)`: Get file content
- `add_info_to_file(to_add: str, fname: str)`: Add data to file
- `get_date()`: Get system date and time
- `set_date(date_string: str)`: Set device date and time
- `finalize_boot()`: Validate board settings post boot
- `get_interface_mtu_size(interface: str)`: Get MTU size of interface

### Hook Implementations

- `boardfarm_device_boot(device_manager)`: Boot the CPE device
- `boardfarm_device_configure()`: Configure boardfarm device
- `boardfarm_shutdown_device()`: Shutdown the CPE device
- `boardfarm_skip_boot()`: Skip boot hook implementation

## bf_lan (LAN Device)

The LAN device represents a client device connected to the LAN side of the CPE.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `LinuxDevice` → `LAN`
- **Implementation**: `LinuxLAN`

### LAN Properties

- `iface_dut` (str): Name of interface connected to DUT
- `lan_gateway` (str): LAN gateway address (default: "192.168.178.1")
- `http_proxy` (str): SOCKS5 Dante proxy address
- `multicast` (Multicast): Multicast component instance
- `console` (BoardfarmPexpect): LAN console
- `firewall` (IptablesFirewall): Firewall component instance
- `nslookup` (NSLookup): NSLookup utility instance
- `nw_utility` (NetworkUtility): Network utility instance
- `ipv4_addr` (str): IPv4 address on IFACE facing DUT
- `ipv6_addr` (str): IPv6 address on IFACE facing DUT

### LAN Methods

#### DHCP Client Management
- `start_ipv4_lan_client(wan_gw, prep_iface)`: Restart IPv4 dhclient to obtain IP
- `start_ipv6_lan_client(wan_gw, prep_iface)`: Restart IPv6 dhclient to obtain IP
- `release_dhcp(interface: str)`: Release IPv4 of interface
- `renew_dhcp(interface: str)`: Renew IPv4 of interface
- `release_ipv6(interface: str, stateless: bool)`: Release IPv6 of interface
- `renew_ipv6(interface: str, stateless: bool)`: Renew IPv6 of interface
- `configure_dhclient_option60(enable: bool)`: Configure DHCP option 60
- `configure_dhclient_option61(enable: bool)`: Configure DHCP option 61
- `configure_dhclient_option125(enable: bool)`: Configure DHCP option 125
- `configure_dhcpv6_option17(enable: bool)`: Configure DHCPv6 option 17

#### Network Interface Operations
- `get_interface_ipv4addr(interface: str)`: Get IPv4 address of interface
- `get_interface_ipv6addr(interface: str)`: Get IPv6 address of interface
- `get_interface_link_local_ipv6addr(interface: str)`: Get link local IPv6 address
- `get_interface_macaddr(interface: str)`: Get interface MAC address
- `get_interface_mask(interface: str)`: Get subnet mask of interface
- `get_interface_mtu_size(interface: str)`: Get MTU size of interface
- `set_link_state(interface: str, state: str)`: Set interface state (up/down)
- `is_link_up(interface: str, pattern: str)`: Check if link is up
- `check_dut_iface()`: Check that DUT interface exists and has carrier

#### Network Testing
- `ping(ping_ip, ping_count, ping_interface, options, timeout, json_output)`: Ping remote host
- `traceroute(host_ip, version, options, timeout)`: Get traceroute output
- `curl(url, protocol, port, options)`: Perform curl action to web service
- `http_get(url, timeout, options)`: Perform HTTP GET and return parsed result
- `dns_lookup(domain_name, record_type, opts)`: Run dig command and return parsed result
- `nmap(ipaddr, ip_type, port, protocol, max_retries, min_rate, opts, timeout)`: Perform nmap operation

#### Packet Capture
- `tcpdump_capture(fname, interface, additional_args)`: Capture packets (context manager)
- `start_tcpdump(interface, port, output_file, filters, additional_filters)`: Start tcpdump capture
- `stop_tcpdump(process_id)`: Stop tcpdump capture
- `tcpdump_read_pcap(fname, additional_args, timeout, rm_pcap)`: Read packet captures from file
- `tshark_read_pcap(fname, additional_args, timeout, rm_pcap)`: Read packet captures using tshark

#### Traffic Generation
- `start_traffic_receiver(traffic_port, bind_to_ip, ip_version, udp_only)`: Start iperf3 server
- `start_traffic_sender(host, traffic_port, bandwidth, bind_to_ip, direction, ip_version, udp_protocol, time, client_port, udp_only)`: Start iperf3 client
- `stop_traffic(pid)`: Stop iPerf3 process
- `get_iperf_logs(log_file)`: Read traffic flow logs

#### Routing
- `get_default_gateway()`: Get default gateway from IP route output
- `set_static_ip(interface, ip_address, netmask)`: Set static IP for LAN
- `del_default_route(interface)`: Remove default gateway
- `set_default_gw(ip_address, interface)`: Set default gateway address

#### UPnP
- `create_upnp_rule(int_port, ext_port, protocol, url)`: Create UPnP rule
- `delete_upnp_rule(ext_port, protocol, url)`: Delete UPnP rule

#### Multicast
- `send_mldv2_report(mcast_group_record, count)`: Send MLDv2 report
- `enable_ipv6()`: Enable IPv6 on connected client interface
- `disable_ipv6()`: Disable IPv6 on connected client interface

#### System Operations
- `get_date()`: Get system date and time
- `set_date(opt, date_string)`: Set device date and time
- `get_hostname()`: Get hostname of device
- `add_hosts_entry(ip, host_name)`: Add entry in hosts file
- `delete_hosts_entry(host_name, ip)`: Delete entry in hosts file
- `flush_arp_cache()`: Flush ARP cache entries
- `get_arp_table()`: Fetch ARP table output
- `delete_arp_table_entry(ip, intf)`: Delete ARP table entry
- `get_process_id(process_name)`: Return process ID
- `kill_process(pid, signal)`: Kill running process
- `delete_file(filename)`: Delete file from device
- `scp_device_file_to_local(local_path, source_path)`: Copy file from server using SCP
- `scp_local_file_to_device(local_path, destination_path)`: Copy local file to server using SCP

#### HTTP Services
- `start_http_service(port, ip_version)`: Start HTTP service on given port
- `stop_http_service(port)`: Stop HTTP service running on given port

#### Network Attacks
- `start_nping(interface_ip, ipv6_flag, extra_args, port_range, hit_count, rate, mode)`: Perform nping
- `stop_nping(process_id)`: Stop nping process
- `hping_flood(protocol, target, packet_count, extra_args, pkt_interval)`: Validate SYN/UDP/ICMP flood
- `netcat(host_ip, port, additional_args)`: Run netcat command

### Hook Implementations

- `boardfarm_attached_device_boot()`: Boot LAN device
- `boardfarm_attached_device_boot_async()`: Boot LAN device (async)
- `boardfarm_skip_boot()`: Initialize LAN device
- `boardfarm_skip_boot_async()`: Initialize LAN device (async)
- `boardfarm_shutdown_device()`: Shutdown LAN device
- `boardfarm_attached_device_configure(config)`: Configure attached device
- `boardfarm_attached_device_configure_async(config)`: Configure attached device (async)
- `contingency_check(env_req, device_manager)`: Make sure LAN is working fine

## bf_wan (WAN Device)

The WAN device represents the network infrastructure on the WAN side of the CPE.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `LinuxDevice` → `WAN`
- **Implementation**: `LinuxWAN`

### WAN Properties

- `iface_dut` (str): Name of interface connected to DUT
- `multicast` (Multicast): Multicast component instance
- `console` (BoardfarmPexpect): WAN console
- `firewall` (IptablesFirewall): Firewall component instance
- `nw_utility` (NetworkUtility): Network utility instance
- `nslookup` (NSLookup): NSLookup utility instance
- `http_proxy` (str): SOCKS5 Dante proxy address
- `rssh_username` (str): WAN username for Reverse SSH
- `rssh_password` (str): WAN password for Reverse SSH
- `ipv4_addr` (str): IPv4 address on IFACE facing DUT
- `ipv6_addr` (str): IPv6 address on IFACE facing DUT

### WAN Methods

#### TFTP Operations
- `copy_local_file_to_tftpboot(local_file_path)`: SCP local file to tftpboot directory
- `download_image_to_tftpboot(image_uri)`: Download image from URL to tftpboot directory

#### SNMP Operations
- `execute_snmp_command(snmp_command, timeout)`: Execute SNMP command

#### Reverse SSH
- `is_connect_to_board_via_reverse_ssh_successful(rssh_username, rssh_password, reverse_ssh_port)`: Perform reverse SSH from jump server to CPE

#### Network Statistics
- `get_network_statistics()`: Execute netstat command to get port status

#### Routing
- `add_route(destination, gw_interface)`: Add route to destination via gateway interface
- `delete_route(destination)`: Delete route to destination

#### Common Network Operations
All methods from `LinuxDevice` are available, including:
- `ping()`, `traceroute()`, `curl()`, `http_get()`, `dns_lookup()`, `nmap()`
- `tcpdump_capture()`, `start_tcpdump()`, `stop_tcpdump()`, `tshark_read_pcap()`
- `start_traffic_receiver()`, `start_traffic_sender()`, `stop_traffic()`, `get_iperf_logs()`
- `get_interface_ipv4addr()`, `get_interface_ipv6addr()`, `get_interface_macaddr()`
- `get_interface_mask()`, `get_interface_mtu_size()`, `set_link_state()`, `is_link_up()`
- `start_http_service()`, `stop_http_service()`
- `get_date()`, `set_date()`, `get_hostname()`
- `release_dhcp()`, `set_static_ip()`, `set_default_gw()`
- `hping_flood()`, `start_nping()`, `stop_nping()`
- `delete_file()`, `scp_device_file_to_local()`
- `get_process_id()`, `kill_process()`

### Hook Implementations

- `boardfarm_server_boot(device_manager)`: Boot WAN device
- `boardfarm_skip_boot()`: Initialize WAN device
- `boardfarm_skip_boot_async()`: Initialize WAN device (async)
- `boardfarm_shutdown_device()`: Shutdown WAN device
- `contingency_check(env_req, device_manager)`: Make sure WAN is working fine

## bf_wlan (WLAN Device)

The WLAN device represents a wireless client device connected to the CPE's WiFi network.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `LinuxDevice` → `WLAN`
- **Implementation**: `LinuxWLAN`

### WLAN Properties

- `iface_dut` (str): Name of WLAN interface (default: "wlan1")
- `band` (str): WiFi band supported (e.g., "2.4", "5", "dual")
- `network` (str): WiFi network to connect to (e.g., "private", "guest", "community")
- `authentication` (str): WiFi authentication method (e.g., "WPA-PSK", "WPA2")
- `protocol` (str): WiFi protocol (e.g., "802.11ac", "802.11")
- `http_proxy` (str): SOCKS5 Dante proxy address
- `lan_network` (IPv4Network): IPv4 WLAN Network
- `lan_gateway` (IPv4Address): WLAN gateway address
- `multicast` (Multicast): Multicast component instance
- `console` (BoardfarmPexpect): WLAN console

### WLAN Methods

#### WiFi Connection Management
- `reset_wifi_iface()`: Disable and enable WiFi interface
- `disable_wifi()`: Disable WiFi interface
- `enable_wifi()`: Enable WiFi interface
- `wifi_client_connect(ssid_name, password, security_mode, bssid)`: Scan for SSID and verify WiFi connectivity
- `is_wlan_connected()`: Verify WiFi is in connected state
- `wifi_disconnect()`: Disconnect WiFi connectivity
- `disconnect_wpa()`: Disconnect wpa supplicant initialization

#### WiFi Configuration
- `set_wlan_scan_channel(channel)`: Change WiFi client scan channel
- `iwlist_supported_channels(wifi_band)`: Get list of WiFi client support channels
- `list_wifi_ssids()`: Return available WiFi SSIDs
- `change_wifi_region(country)`: Change WiFi region

#### Monitor Mode
- `enable_monitor_mode()`: Enable monitor mode on WLAN interface
- `disable_monitor_mode()`: Disable monitor mode on WLAN interface
- `is_monitor_mode_enabled()`: Check if monitor mode is enabled

#### DHCP Client
- `dhcp_release_wlan_iface()`: DHCP release of WiFi interface
- `start_ipv4_wlan_client()`: Restart IPv4 dhclient to obtain IP
- `start_ipv6_wlan_client()`: Restart IPv6 dhclient to obtain IP

#### IPv6 Management
- `enable_ipv6()`: Enable IPv6 on connected client interface
- `disable_ipv6()`: Disable IPv6 on connected client interface

#### Common Operations
All methods from `LinuxDevice` are available, including:
- `ping()`, `traceroute()`, `curl()`, `http_get()`, `dns_lookup()`
- `get_interface_ipv4addr()`, `get_interface_ipv6addr()`, `get_interface_macaddr()`
- `get_interface_mtu_size()`, `set_link_state()`, `is_link_up()`
- `create_upnp_rule()`, `delete_upnp_rule()`
- `get_default_gateway()`, `get_hostname()`

### Hook Implementations

- `boardfarm_attached_device_boot()`: Boot WLAN device
- `boardfarm_attached_device_boot_async()`: Boot WLAN device (async)
- `boardfarm_shutdown_device()`: Shutdown WLAN device
- `boardfarm_skip_boot()`: Initialize WLAN device
- `boardfarm_attached_device_configure(device_manager, config)`: Configure attached device

## bf_acs (ACS Device)

The ACS (Auto Configuration Server) device manages TR-069/TR-181 operations for CPE devices.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `LinuxDevice` → `ACS`
- **Implementation**: `GenieACS`

### ACS Properties

- `url` (str): ACS URL used (raises NotImplementedError)

### ACS Methods

#### TR-069 RPC Operations
- `GPV(param, timeout, cpe_id)`: Send GetParameterValues command via ACS server
- `SPV(param_value, timeout, cpe_id)`: Execute SetParameterValues RPC call
- `GPA(param, cpe_id)`: Execute GetParameterAttributes RPC call
- `SPA(param, notification_param, access_param, access_list, cpe_id)`: Execute SetParameterAttributes RPC call
- `GPN(param, next_level, timeout, cpe_id)`: Execute GetParameterNames RPC call
- `AddObject(param, param_key, cpe_id)`: Execute AddObject RPC call
- `DelObject(param, param_key, cpe_id)`: Execute DeleteObject RPC call

#### Device Management
- `Reboot(CommandKey, cpe_id)`: Execute Reboot RPC
- `FactoryReset(cpe_id)`: Execute FactoryReset RPC
- `ScheduleInform(CommandKey, DelaySeconds, cpe_id)`: Execute ScheduleInform RPC
- `GetRPCMethods(cpe_id)`: Execute GetRPCMethods RPC
- `Download(url, filetype, targetfilename, filesize, username, password, commandkey, delayseconds, successurl, failureurl, cpe_id)`: Execute Download RPC

#### Provisioning
- `provision_cpe_via_tr069(tr069provision_api_list, cpe_id)`: Provision CPE with TR-069 parameters

#### Common Operations
- `delete_file(filename)`: Delete file from device (raises NotImplementedError)
- `scp_device_file_to_local(local_path, source_path)`: Copy file from server (raises NotImplementedError)
- `console`: Returns ACS console (raises NotSupportedError)
- `firewall`: Returns Firewall instance (raises NotSupportedError)

### Hook Implementations

- `boardfarm_skip_boot()`: Initialize ACS device with skip-boot option
- `boardfarm_server_boot()`: Boot ACS device
- `boardfarm_shutdown_device()`: Shutdown ACS device
- `contingency_check(env_req)`: Make sure ACS is able to read CPE/TR069 client params

## bf_dhcp (Provisioner Device)

The Provisioner device provides DHCP services for CPE provisioning.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `Provisioner`
- **Implementation**: `KeaProvisioner`

### Provisioner Properties

- `iface_dut` (str): Name of interface connected to DUT
- `console` (BoardfarmPexpect): Provisioner console
- `firewall` (IptablesFirewall): Firewall component instance
- `_supported_vsio_options` (list): List of VSIO supported suboptions
- `_supported_vivso_options` (dict): Vendor ID and VIVSO sub-options

### Provisioner Methods

#### CPE Provisioning
- `provision_cpe(cpe_mac, dhcpv4_options, dhcpv6_options)`: Configure KEA provisioner with CPE values

#### Packet Capture
- `tshark_read_pcap(fname, additional_args, timeout, rm_pcap)`: Read packet captures from file
- `start_tcpdump(interface, port, output_file, filters, additional_filters)`: Start tcpdump capture
- `stop_tcpdump(process_id)`: Stop tcpdump capture

#### File Operations
- `scp_device_file_to_local(local_path, source_path)`: Copy file from server using SCP
- `delete_file(filename)`: Delete file from device

### Hook Implementations

- `boardfarm_server_boot()`: Boot KEA provisioner
- `boardfarm_skip_boot()`: Initialize KEA provisioner
- `boardfarm_shutdown_device()`: Shutdown KEA provisioner
- `contingency_check()`: Make sure KeaProvisioner is working fine
- `boardfarm_server_configure(device_manager)`: Configure KEA provisioner

## bf_tftp (TFTP Device)

The TFTP device provides TFTP file transfer services.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `LinuxDevice` → `TFTP`
- **Implementation**: `LinuxTFTP`

### TFTP Methods

TFTP device inherits all methods from `LinuxDevice` and provides TFTP-specific functionality for firmware downloads and file transfers.

## bf_kamailio (SIP Server Device)

The Kamailio device provides SIP server functionality for voice testing.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `LinuxDevice` → `SIPServer`
- **Implementation**: `SIPcenterKamailio5`

SIP server device provides SIP protocol handling and call routing capabilities.

## bf_phone (SIP Phone Device)

The SIP Phone device represents a VoIP phone client.

### Class Hierarchy

- **Base**: `BoardfarmDevice` → `LinuxDevice` → `SIPPhone`
- **Implementation**: `PJSIPPhone`

SIP phone device provides VoIP client functionality for making and receiving calls.

## Base Classes

### BoardfarmDevice

Base class for all Boardfarm devices.

**Properties:**
- `config` (dict): Device configuration
- `device_name` (str): Name of the device
- `device_type` (str): Type of the device

**Methods:**
- `get_interactive_consoles()`: Get interactive consoles from device

### LinuxDevice

Base class for Linux-based devices, extends `BoardfarmDevice`.

**Properties:**
- `eth_interface` (str): Ethernet interface name (default: "eth1")
- `ipv4_addr` (str): IPv4 address on IFACE facing DUT
- `ipv6_addr` (str): IPv6 address on IFACE facing DUT

**Methods:**
- `_connect()`: Establish connection to device via SSH
- `_connect_async()`: Establish connection (async)
- `_disconnect()`: Disconnect SSH connection
- `get_interactive_consoles()`: Get interactive consoles
- `clear_cache()`: Clear all cached properties
- `get_eth_interface_ipv4_address()`: Get eth interface IPv4 address
- `get_eth_interface_ipv6_address(address_type)`: Get eth interface IPv6 address
- `get_interface_ipv4addr(interface)`: Get IPv4 address of interface
- `get_interface_ipv6addr(interface)`: Get IPv6 address of interface
- `get_interface_link_local_ipv6addr(interface)`: Get link local IPv6 address
- `get_interface_macaddr(interface)`: Get interface MAC address
- `get_interface_mask(interface)`: Get subnet mask of interface
- `set_link_state(interface, state)`: Set interface state
- `is_link_up(interface, pattern)`: Check if link is up
- `ping(ping_ip, ping_count, ping_interface, options, timeout, json_output)`: Ping remote host
- `traceroute(host_ip, version, options, timeout)`: Get traceroute output
- `curl(url, protocol, port, options)`: Perform curl action
- `start_http_service(port, ip_version)`: Start HTTP service
- `stop_http_service(port)`: Stop HTTP service
- `http_get(url, timeout, options)`: Perform HTTP GET
- `dns_lookup(domain_name, record_type, opts)`: Run dig command
- `nmap(ipaddr, ip_type, port, protocol, max_retries, min_rate, opts, timeout)`: Perform nmap
- `tcpdump_capture(fname, interface, additional_args)`: Capture packets (context manager)
- `start_tcpdump(interface, port, output_file, filters, additional_filters)`: Start tcpdump
- `stop_tcpdump(process_id)`: Stop tcpdump
- `tcpdump_read_pcap(fname, additional_args, timeout, rm_pcap)`: Read pcap file
- `tshark_read_pcap(fname, additional_args, timeout, rm_pcap)`: Read pcap using tshark
- `release_dhcp(interface)`: Release IPv4 of interface
- `renew_dhcp(interface)`: Renew IPv4 of interface
- `release_ipv6(interface, stateless)`: Release IPv6 of interface
- `renew_ipv6(interface, stateless)`: Renew IPv6 of interface
- `start_traffic_receiver(traffic_port, bind_to_ip, ip_version, udp_only)`: Start iperf3 server
- `start_traffic_sender(host, traffic_port, bandwidth, bind_to_ip, direction, ip_version, udp_protocol, time, client_port, udp_only)`: Start iperf3 client
- `stop_traffic(pid)`: Stop iPerf3 process
- `get_iperf_logs(log_file)`: Read iperf logs
- `delete_file(filename)`: Delete file from device
- `get_date()`: Get system date and time
- `set_date(opt, date_string)`: Set device date and time
- `send_mldv2_report(mcast_group_record, count)`: Send MLDv2 report
- `set_static_ip(interface, ip_address, netmask)`: Set static IP
- `del_default_route(interface)`: Remove default gateway
- `set_default_gw(ip_address, interface)`: Set default gateway
- `start_nping(interface_ip, ipv6_flag, extra_args, port_range, hit_count, rate, mode)`: Perform nping
- `stop_nping(process_id)`: Stop nping
- `hping_flood(protocol, target, packet_count, extra_args, pkt_interval)`: Validate flood operation
- `hostname()`: Get hostname of device
- `get_process_id(process_name)`: Return process ID
- `kill_process(pid, signal)`: Terminate process
- `scp_device_file_to_local(local_path, source_path)`: Copy file from server using SCP
- `scp_local_file_to_device(local_path, destination_path)`: Copy local file to server using SCP
- `download_file_from_uri(file_uri, destination_dir, internet_access_cmd)`: Download file from URI
- `start_danteproxy()`: Start Dante server for SOCKS5 proxy
- `stop_danteproxy()`: Stop Dante proxy
- `stop_danteproxy_async()`: Stop Dante proxy (async)

## Notes

- All device types can be accessed through the DeviceManager after Boardfarm initialization
- Many methods have both synchronous and asynchronous versions (indicated by `_async` suffix)
- Device-specific options can be configured via the `options` field in the device configuration
- Hook implementations allow devices to participate in Boardfarm's boot and configuration lifecycle
- Contingency checks can be performed to verify device readiness before test execution

