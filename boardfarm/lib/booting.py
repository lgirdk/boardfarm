# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time
import warnings
from collections import OrderedDict

import boardfarm.exceptions
import debtcollector
from boardfarm.lib.common import run_once

warnings.simplefilter("always", UserWarning)


@run_once
def flash_meta_helper(board, meta, wan, lan):
    """Flash meta helper."""
    board.flash_meta(meta, wan, lan, check_version=True)


def flash_image(config,
                env_helper,
                board,
                lan,
                wan,
                tftp_device,
                reflash=True):
    """Flash image on board."""
    rootfs = None

    # Reflash only if at least one or more of these
    # variables are set, or else there is nothing to do in u-boot
    meta_interrupt = False
    if (config.META_BUILD
            or env_helper.has_image()) and not board.flash_meta_booted:
        meta_interrupt = True
    if reflash and any([
            meta_interrupt,
            config.ROOTFS,
            config.KERNEL,
            config.UBOOT,
            config.COMBINED,
            config.ATOM,
            config.ARM,
    ]):
        # Break into U-Boot, set environment variables
        board.wait_for_boot()
        board.setup_uboot_network(tftp_device.gw)
        if config.META_BUILD:
            for _ in range(3):
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
                raise Exception("Error during flashing...")
        if config.UBOOT:
            board.flash_uboot(config.UBOOT)
        if config.COMBINED:
            board.flash_all(config.COMBINED)
        if config.ROOTFS:
            # save filename for cases where we didn't flash it
            # but will use it later to load from memory
            rootfs = board.flash_rootfs(config.ROOTFS)
        if config.NFSROOT:
            board.prepare_nfsroot(config.NFSROOT)
        if config.KERNEL:
            board.flash_linux(config.KERNEL)
        if config.ARM:
            board.flash_arm(config.ARM)
        if config.ATOM:
            board.flash_atom(config.ATOM)
        # Boot from U-Boot to Linux
        board.boot_linux(rootfs=rootfs, bootargs=config.bootargs)


def boot_image(config, env_helper, board, lan, wan, tftp_device):
    """Boot image."""
    def _meta_flash(img):
        """Flash with image."""
        try:
            flash_meta_helper(board, img, wan, lan)
        except Exception as e:
            print(e)
            tftp_device.restart_tftp_server()
            board.reset(break_into_uboot=True)
            board.setup_uboot_network(tftp_device.gw)

    def _factory_reset(img):
        """Reset using factory_reset method."""
        board.factory_reset()

    methods = {
        "meta_build": _meta_flash,
        "rootfs": board.flash_rootfs,
        "kernel": board.flash_linux,
        "atom": board.flash_atom,
        "arm": board.flash_arm,
        "all": board.flash_all,
        "factory_reset": _factory_reset,
    }

    def _perform_flash(boot_sequence):
        """Perform Flash booting."""
        for i in boot_sequence:
            for strategy, img in i.items():
                if strategy in ["factory_reset", "meta_build"]:
                    board.wait_for_linux()
                else:
                    board.wait_for_boot()

                board.setup_uboot_network(tftp_device.gw)
                result = methods[strategy](img)
                rootfs = None
                if strategy == "rootfs":
                    rootfs = result

                if strategy in ["factory_reset", "meta_build"]:
                    if not result:
                        board.reset()
                else:
                    board.boot_linux(rootfs=rootfs, bootargs=config.bootargs)

    def _check_override(strategy, img):
        """Check for Overriding image value."""
        if getattr(config, strategy.upper(), None):
            # this is the override
            debtcollector.deprecate(
                "Warning!!! cmd line arg has been passed."
                "Overriding image value for {}".format(strategy),
                removal_version="> 1.1.1",
                category=UserWarning,
            )

            return getattr(config, strategy.upper())
        return img

    boot_sequence = []
    stage = OrderedDict()
    stage[1] = OrderedDict()
    stage[2] = OrderedDict()

    if config.META_BUILD:
        strategy = "meta_build"
        stage[2].update({"meta_build": config.META_BUILD})
    elif any([config.ARM, config.ATOM, config.COMBINED]):
        count = 0
        if config.COMBINED:
            strategy = "all"
            count += 1
            stage[2]["all"] = config.COMBINED
        if config.ATOM:
            strategy = "atom"
            count += 1
            stage[2]["atom"] = config.ATOM
        if config.ARM:
            count += 1
            strategy = "arm"
            stage[2]["arm"] = config.ARM

        assert count != 3, "You can't have ARM, ATOM and COMBINED TOGETHER!!!"
    else:
        if config.ROOTFS:
            strategy = "rootfs"
            stage[2]["rootfs"] = config.ROOTFS
        if config.KERNEL:
            strategy = "kernel"
            stage[2]["kernel"] = config.KERNEL

    if not stage[2]:
        d = env_helper.get_dependent_software()
        if d:
            fr = d.get("factory_reset", False)
            if fr:
                stage[1]["factory_reset"] = fr
            strategy = d.get("flash_strategy")
            img = _check_override(strategy, d.get("image_uri"))
            stage[1][strategy] = img

    if not stage[2]:
        d = env_helper.get_software()
        if d:
            fr = d.get("factory_reset", False)
            if fr:
                stage[2]["factory_reset"] = fr
            if "load_image" in d:
                strategy = "meta_build"
                img = _check_override(strategy, d.get("load_image"))
            else:
                strategy = d.get("flash_strategy")
                img = _check_override(strategy, d.get("image_uri"))

            if stage[1]:
                assert (strategy != "meta_build"
                        ), "meta_build strategy needs to run alone!!!"

            stage[2][strategy] = img

    for k, v in stage[1].items():
        boot_sequence.append({k: v})
    for k, v in stage[2].items():
        boot_sequence.append({k: v})

    if boot_sequence:
        _perform_flash(boot_sequence)


def get_tftp(config):
    """Get tftp server details."""
    # start tftpd server on appropriate device
    tftp_servers = [
        x["name"] for x in config.board["devices"]
        if "tftpd-server" in x.get("options", "")
    ]
    tftp_device = None
    # start all tftp servers for now
    for tftp_server in tftp_servers:
        # This is a mess, just taking the last tftpd-server?
        tftp_device = getattr(config, tftp_server)
    return tftp_device, tftp_servers


def start_dhcp_servers(config):
    """Start DHCP server."""
    # start dhcp servers
    for device in config.board["devices"]:
        if "options" in device and "no-dhcp-sever" in device["options"]:
            continue
        if "options" in device and "dhcp-server" in device["options"]:
            getattr(config, device["name"]).setup_dhcp_server()


def provision(board, prov, wan, tftp_device):
    """Board Provisioning."""
    prov.tftp_device = tftp_device
    board.reprovision(prov)

    if hasattr(prov, "prov_gateway"):
        gw = prov.prov_gateway if wan.gw in prov.prov_network else prov.prov_ip

        for nw in [prov.cm_network, prov.mta_network, prov.open_network]:
            wan.sendline("ip route add %s via %s" % (nw, gw))
            wan.expect(wan.prompt)

    # TODO: don't do this and sort out two interfaces with ipv6
    wan.disable_ipv6("eth0")

    if hasattr(prov, "prov_gateway_v6"):
        wan.sendline("ip -6 route add default via %s" %
                     str(prov.prov_gateway_v6))
        wan.expect(wan.prompt)

    wan.sendline("ip route")
    wan.expect(wan.prompt)
    wan.sendline("ip -6 route")
    wan.expect(wan.prompt)


def boot(config,
         env_helper,
         devices,
         reflash=True,
         logged=dict(),
         flashing_image=True):
    """Define Boot method for configuring to device."""
    logged["boot_step"] = "start"

    board = devices.board
    wan = devices.wan
    lan = devices.lan
    tftp_device, tftp_servers = get_tftp(config)
    logged["boot_step"] = "tftp_device_assigned"

    start_dhcp_servers(config)
    logged["boot_step"] = "dhcp_server_started"

    if not wan and len(tftp_servers) == 0:
        raise boardfarm.exceptions.NoTFTPServer

    # This still needs some clean up, the fall back is to assuming the
    # WAN provides the tftpd server, but it's not always the case
    if wan:
        wan.configure(kind="wan_device", config=config)
        if tftp_device is None:
            tftp_device = wan

    logged["boot_step"] = "wan_device_configured"

    tftp_device.start_tftp_server()

    prov = getattr(config, "provisioner", None)
    if prov is not None:
        provision(board, prov, wan, tftp_device)
        logged["boot_step"] = "board_provisioned"
    else:
        logged["boot_step"] = "board_provisioned_skipped"

    if lan:
        lan.configure(kind="lan_device")
    logged["boot_step"] = "lan_device_configured"

    # tftp_device is always None, so we can set it from config
    board.tftp_server = tftp_device.ipaddr
    # then these are just hard coded defaults
    board.tftp_port = 22
    # but are user/password used for tftp, they are likely legacy and just need to go away
    board.tftp_username = "root"
    board.tftp_password = "bigfoot1"

    board.reset()
    logged["boot_step"] = "board_reset_ok"
    if flashing_image:
        flash_image(config, env_helper, board, lan, wan, tftp_device, reflash)
    else:
        boot_image(config, env_helper, board, lan, wan, tftp_device)
    logged["boot_step"] = "flash_ok"
    if hasattr(board, "pre_boot_linux"):
        board.pre_boot_linux(wan=wan, lan=lan)
    board.linux_booted = True
    logged["boot_step"] = "boot_ok"
    board.wait_for_linux()
    logged["boot_step"] = "linux_ok"

    if flashing_image:
        if config.META_BUILD and board.flash_meta_booted:
            flash_meta_helper(board, config.META_BUILD, wan, lan)
            logged["boot_step"] = "late_flash_meta_ok"
        elif (env_helper.has_image() and board.flash_meta_booted
              and not config.ROOTFS and not config.KERNEL):
            flash_meta_helper(board, env_helper.get_image(), wan, lan)
            logged["boot_step"] = "late_flash_meta_ok"

    linux_booted_seconds_up = board.get_seconds_uptime()
    # Retry setting up wan protocol
    if config.setup_device_networking:
        for _ in range(2):
            time.sleep(10)
            try:
                if "pppoe" in config.WAN_PROTO:
                    wan.turn_on_pppoe()
                board.config_wan_proto(config.WAN_PROTO)
                break
            except Exception:
                print("\nFailed to check/set the router's WAN protocol.")
        board.wait_for_network()
    board.wait_for_mounts()
    logged["boot_step"] = "network_ok"

    # Give other daemons time to boot and settle
    if config.setup_device_networking:
        for _ in range(5):
            board.get_seconds_uptime()
            time.sleep(5)

    try:
        board.set_password(password="password")
    except Exception:
        print("WARNING: Unable to set root password on router.")

    board.sendline("cat /proc/cmdline")
    board.expect(board.prompt)
    board.sendline("uname -a")
    board.expect(board.prompt)

    # we can't have random messsages messages
    board.set_printk()

    if hasattr(config, "INSTALL_PKGS") and config.INSTALL_PKGS != "":
        for pkg in config.INSTALL_PKGS.split(" "):
            if len(pkg) > 0:
                board.install_package(pkg)

    if board.has_cmts:
        board.check_valid_docsis_ip_networking()

    # Try to verify router has stayed up (and, say, not suddenly rebooted)
    end_seconds_up = board.get_seconds_uptime()
    print("\nThe router has been up %s seconds." % end_seconds_up)
    if config.setup_device_networking:
        assert end_seconds_up > linux_booted_seconds_up

    logged["boot_step"] = "boot_ok"
    logged["boot_time"] = end_seconds_up

    for i, v in enumerate(board.dev.lan_clients):
        if getattr(env_helper, "has_lan_advertise_identity", None):
            if env_helper.has_lan_advertise_identity(i):
                v.add_lan_advertise_identity_cfg(i)
            else:
                v.remove_lan_advertise_identity_cfg()

    if board.routing and lan and config.setup_device_networking:
        if wan is not None:
            lan.start_lan_client(wan_gw=wan.gw)
        else:
            lan.start_lan_client()

    logged["boot_step"] = "lan_ok"
