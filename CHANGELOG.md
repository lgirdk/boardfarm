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
