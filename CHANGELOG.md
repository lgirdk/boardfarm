## 2022.15.0 (2022-04-14)

### Fix

- remove yamlfmt/yamllint from pre-commit
- bumps the env version
- **pre-commit**: update pre-commit hooks to latest versions and autofix issues

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

## 2022.13.0 (2022-03-31)

### Feat

- **use_cases:console.py**: implement usecase to restart the erouter interface
- **linux.py,networking.py**: add support to set static ip , ip search in pool
- **contingency_checks.py**: add support to disable lan client init
- **wifi_use_cases**: update access to wifi object getter, change the usage in use cases

### Fix

- **pyproject.toml**: freeze pylint dependency to last working version

### Refactor

- **dockerfiles**: Create dockerfile for each device and cleanup

### BREAKING CHANGE

- BOARDFARM-1734

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

### BREAKING CHANGE

- Do not merge until all the executors have been updated!
BOARDFARM-1698
- BOARDFARM-1500

## 2022.07.0 (2022-02-16)

### Refactor

- **pyproject.toml**: freeze selenium dependency to 4.1.0

### Feat

- **quagga_router.py**: add quagga router device class
- **linux.py**: add support for tcpdump capture,read[tcpdump,tshark]
- **traffic_generator.py**: formalise traffic generator template
- **debian_lan**: add iw and wpasupplicant packages in image

### Fix

- **pyproject.toml**: freeze pyvirtualdisplay package version to 2.2
- **pyproject.toml**: pin elasticsearch to stay compliant with api
- increase cli size

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

### BREAKING CHANGE

- BOARDFARM-1456

## 2022.01.0 (2022-01-05)

### Feat

- get image use image_uri
- **multicast**: add multicast usecases
- **quagga**: add mrouted daemon

### BREAKING CHANGE

- If using Docsis devices the latest Docsis change must be picked.

### Fix

- **boardfarm:resources:configs:kamailio.cfg**: update kamailio.cfg to configure timeout of 25sec
- **boardfarm:devices:debian_isc.py**: fix acs url in vendor specific dhcpoptions to use http as prefix
- **boardfarm:use_cases:voice.py**: handle exception for hangup in shutdown_phone usecase

## 2021.51.0 (2021-12-22)

### Fix

- **devices:linux.py**: add fix to fetch erouter0/lan ipv6 on linux console when output is delayed/untidy after command execution
- do not use get_pytest_name yet
- fix test name fetching in acs intercept
- **devices:debian_lan.py**: handle timeout error when tshark read is too long for failed lan renewal

### Feat

- **quagga-pim**: add IGMP multicast routing for interface
- enable/disable acs pcap capture
- improved name discovery

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
