# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time
import warnings

import boardfarm.exceptions
from boardfarm.lib.common import run_once

warnings.simplefilter("always", UserWarning)


@run_once
def flash_meta_helper(board, meta, wan, lan):
    board.flash_meta(meta, wan, lan, check_version=True)


def flash_image(config,
                env_helper,
                board,
                lan,
                wan,
                tftp_device,
                reflash=True):
    rootfs = None

    # Reflash only if at least one or more of these
    # variables are set, or else there is nothing to do in u-boot
    meta_interrupt = False
    if (config.META_BUILD or env_helper.has_image()) \
            and not board.flash_meta_booted:
        meta_interrupt = True
    if reflash and (meta_interrupt or config.ROOTFS or\
            config.KERNEL or config.UBOOT):
        # Break into U-Boot, set environment variables
        board.wait_for_boot()
        board.setup_uboot_network(tftp_device.gw)
        if config.META_BUILD:
            for attempt in range(3):
                try:
                    if config.META_BUILD:
                        flash_meta_helper(board, config.META_BUILD, wan, lan)
                    elif not config.ROOTFS and not config.KERNEL:
                        flash_meta_helper(board, env_helper.get_image(), wan,
                                          lan)
                    break
                except Exception as e:
                    print(e)
                    tftp_device.restart_tftp_server()
                    board.reset(break_into_uboot=True)
                    board.setup_uboot_network(tftp_device.gw)
            else:
                raise Exception('Error during flashing...')
        if config.UBOOT:
            board.flash_uboot(config.UBOOT)
        if config.ROOTFS:
            # save filename for cases where we didn't flash it
            # but will use it later to load from memory
            rootfs = board.flash_rootfs(config.ROOTFS)
        if config.NFSROOT:
            board.prepare_nfsroot(config.NFSROOT)
        if config.KERNEL:
            board.flash_linux(config.KERNEL)
        # Boot from U-Boot to Linux
        board.boot_linux(rootfs=rootfs, bootargs=config.bootargs)


def get_tftp(config):
    # start tftpd server on appropriate device
    tftp_servers = [
        x['name'] for x in config.board['devices']
        if 'tftpd-server' in x.get('options', "")
    ]
    tftp_device = None
    # start all tftp servers for now
    for tftp_server in tftp_servers:
        # This is a mess, just taking the last tftpd-server?
        tftp_device = getattr(config, tftp_server)
    return tftp_device, tftp_servers


def start_dhcp_servers(config):
    # start dhcp servers
    for device in config.board['devices']:
        if 'options' in device and 'no-dhcp-sever' in device['options']:
            continue
        if 'options' in device and 'dhcp-server' in device['options']:
            getattr(config, device['name']).setup_dhcp_server()


def provision(board, prov, wan, tftp_device):
    prov.tftp_device = tftp_device
    board.reprovision(prov)

    if hasattr(prov, 'prov_gateway'):
        gw = prov.prov_gateway if wan.gw in prov.prov_network else prov.prov_ip

        for nw in [prov.cm_network, prov.mta_network, prov.open_network]:
            wan.sendline('ip route add %s via %s' % (nw, gw))
            wan.expect(wan.prompt)

    # TODO: don't do this and sort out two interfaces with ipv6
    wan.disable_ipv6('eth0')

    if hasattr(prov, 'prov_gateway_v6'):
        wan.sendline('ip -6 route add default via %s' %
                     str(prov.prov_gateway_v6))
        wan.expect(wan.prompt)

    wan.sendline('ip route')
    wan.expect(wan.prompt)
    wan.sendline('ip -6 route')
    wan.expect(wan.prompt)


def boot(config, env_helper, devices, reflash=True, logged=dict()):
    logged['boot_step'] = "start"

    board = devices.board
    wan = devices.wan
    lan = devices.lan
    tftp_device, tftp_servers = get_tftp(config)
    logged['boot_step'] = "tftp_device_assigned"

    start_dhcp_servers(config)
    logged['boot_step'] = "dhcp_server_started"

    if not wan and len(tftp_servers) == 0:
        raise boardfarm.exceptions.NoTFTPServer

    # This still needs some clean up, the fall back is to assuming the
    # WAN provides the tftpd server, but it's not always the case
    if wan:
        wan.configure(kind="wan_device", config=config)
        if tftp_device is None:
            tftp_device = wan

    logged['boot_step'] = "wan_device_configured"

    tftp_device.start_tftp_server()

    prov = getattr(config, 'provisioner', None)
    if prov is not None:
        provision(board, prov, wan, tftp_device)
        logged['boot_step'] = "board_provisioned"
    else:
        logged['boot_step'] = "board_provisioned_skipped"

    if lan:
        lan.configure(kind="lan_device")
    logged['boot_step'] = "lan_device_configured"

    # tftp_device is always None, so we can set it from config
    board.tftp_server = tftp_device.ipaddr
    # then these are just hard coded defaults
    board.tftp_port = 22
    # but are user/password used for tftp, they are likely legacy and just need to go away
    board.tftp_username = "root"
    board.tftp_password = "bigfoot1"

    board.reset()
    logged['boot_step'] = "board_reset_ok"
    flash_image(config, env_helper, board, lan, wan, tftp_device, reflash)
    logged['boot_step'] = "flash_ok"
    if hasattr(board, "pre_boot_linux"):
        board.pre_boot_linux(wan=wan, lan=lan)
    board.linux_booted = True
    logged['boot_step'] = "boot_ok"
    board.wait_for_linux()
    logged['boot_step'] = "linux_ok"

    if config.META_BUILD and board.flash_meta_booted:
        flash_meta_helper(board, config.META_BUILD, wan, lan)
        logged['boot_step'] = "late_flash_meta_ok"
    elif env_helper.has_image() and board.flash_meta_booted \
            and not config.ROOTFS and not config.KERNEL:
        flash_meta_helper(board, env_helper.get_image(), wan, lan)
        logged['boot_step'] = "late_flash_meta_ok"

    linux_booted_seconds_up = board.get_seconds_uptime()
    # Retry setting up wan protocol
    if config.setup_device_networking:
        for i in range(2):
            time.sleep(10)
            try:
                if "pppoe" in config.WAN_PROTO:
                    wan.turn_on_pppoe()
                board.config_wan_proto(config.WAN_PROTO)
                break
            except:
                print("\nFailed to check/set the router's WAN protocol.")
        board.wait_for_network()
    board.wait_for_mounts()
    logged['boot_step'] = "network_ok"

    # Give other daemons time to boot and settle
    if config.setup_device_networking:
        for i in range(5):
            board.get_seconds_uptime()
            time.sleep(5)

    try:
        board.set_password(password='password')
    except:
        print("WARNING: Unable to set root password on router.")

    board.sendline('cat /proc/cmdline')
    board.expect(board.prompt)
    board.sendline('uname -a')
    board.expect(board.prompt)

    # we can't have random messsages messages
    board.set_printk()

    if hasattr(config, 'INSTALL_PKGS') and config.INSTALL_PKGS != "":
        for pkg in config.INSTALL_PKGS.split(' '):
            if len(pkg) > 0:
                board.install_package(pkg)

    if board.has_cmts:
        board.check_valid_docsis_ip_networking()

    # Try to verify router has stayed up (and, say, not suddenly rebooted)
    end_seconds_up = board.get_seconds_uptime()
    print("\nThe router has been up %s seconds." % end_seconds_up)
    if config.setup_device_networking:
        assert end_seconds_up > linux_booted_seconds_up

    logged['boot_step'] = "boot_ok"
    logged['boot_time'] = end_seconds_up

    if board.routing and lan and config.setup_device_networking:
        if wan is not None:
            lan.start_lan_client(wan_gw=wan.gw)
        else:
            lan.start_lan_client()

    logged['boot_step'] = "lan_ok"
