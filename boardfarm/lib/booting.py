"""Boot module forgeneric devices."""
import logging
import time
import traceback
import warnings

from termcolor import colored

import boardfarm.lib.voice
from boardfarm.devices.debian_lan import DebianLAN
from boardfarm.exceptions import (
    BootFail,
    CodeError,
    DeviceDoesNotExistError,
    NoTFTPServer,
)
from boardfarm.lib.booting_utils import check_and_connect_to_wifi
from boardfarm.lib.common import retry_on_exception
from boardfarm.library import check_devices

logger = logging.getLogger("bft")


def get_tftp(config):
    """Get tftp server details."""
    # start tftpd server on appropriate device
    tftp_servers = [
        x["name"]
        for x in config.board["devices"]
        if "tftpd-server" in x.get("options", "")
    ]
    tftp_device = None
    # start all tftp servers for now
    for tftp_server in tftp_servers:
        # This is a mess, just taking the last tftpd-server?
        tftp_device = getattr(config, tftp_server)
    return tftp_device, tftp_servers


def pre_boot_wan_clients(config, env_helper, devices):

    tftp_device, tftp_servers = boardfarm.lib.booting.get_tftp(config)
    if not tftp_servers:
        logger.error(colored("No tftp server found", color="red", attrs=["bold"]))
        # currently we must have at least 1 tftp server configured
        raise NoTFTPServer
    if len(tftp_servers) > 1:
        msg = f"Found more than 1 tftp server: {tftp_servers}, using {tftp_device.name}"
        logger.error(colored(msg, color="red", attrs=["bold"]))
        raise CodeError(msg)

    # should we run configure for all the wan devices? or just wan?
    for x in devices:
        # if isinstance(x, DebianWAN): # does not work for mitm
        if hasattr(x, "name") and "wan" in x.name:
            logger.info(f"Configuring {x.name}")
            x.configure(config=config)
    # if more than 1 tftp server should we start them all?
    # currently starting the 1 being used
    logger.info(f"Starting TFTP server on {tftp_device.name}")
    tftp_device.start_tftp_server()
    devices.board.tftp_device = tftp_device


def pre_boot_lan_clients(config, env_helper, devices):
    for x in devices.lan_clients:
        if isinstance(x, DebianLAN):
            logger.info(f"Configuring {x.name}")
            x.configure()


def pre_boot_wlan_clients(config, env_helper, devices):
    for x in getattr(devices, "wlan_clients", []):
        logger.info(f"Configuring {x.name}")
        x.configure()


def pre_boot_board(config, env_helper, devices):
    pass


def pre_boot_env(config, env_helper, devices):
    # this should take care of provisioner/tr069/voice/etc
    # depending on what the env_helperd has configured
    if env_helper.mitm_enabled() and not hasattr(devices, "mitm"):
        raise DeviceDoesNotExistError("No mitm device (requested by environment)")

    if env_helper.voice_enabled():
        try:
            for voice_device in devices.get_device_array(
                "softphones"
            ) + devices.get_device_array("FXS"):
                voice_device.phone_config(devices.sipcenter.gw)
            devices.sipcenter.configure_endpoint_transport(
                [devices.fxs1.own_number, devices.fxs2.own_number]
            )
        except AttributeError as error:
            raise DeviceDoesNotExistError(
                f"Voice is not supported in this board. {str(error)}"
            )

    prov = getattr(config, "provisioner", None)
    if prov:
        if env_helper.vendor_encap_opts(ip_proto="ipv4"):
            devices.provisioner.vendor_opts_acsv4_url = True
        if env_helper.vendor_encap_opts(ip_proto="ipv6"):
            devices.provisioner.vendor_opts_acsv6_url = True
        logger.info("Provisioning board")
        # provision_board() TBD
    else:
        # should this be an error?
        logger.warning(
            colored(
                "No provisioner found! Board provisioned skipped",
                color="yellow",
                attrs=["bold"],
            )
        )


pre_boot_actions = {
    "wan_clients_pre_boot": pre_boot_wan_clients,
    "lan_clients_pre_boot": pre_boot_lan_clients,
    "wlan_clients_pre_boot": pre_boot_wlan_clients,
    "board_pre_boot": pre_boot_board,
    "environment_pre_boot": pre_boot_env,
}


def boot_board(config, env_helper, devices):
    try:
        devices.board.reset()
        if env_helper.get_software():
            devices.board.flash(env_helper)
            # store the timestamp, for uptime check later (in case the board
            # crashes on boot)
            devices.board.__reset__timestamp = time.time()
            devices.board.reset()
            for _ in range(5):
                devices.board.touch()
                time.sleep(10)
    except Exception as e:
        logger.critical(colored("\n\nFailed to Boot", color="red", attrs=["bold"]))
        logger.error(e)
        raise BootFail("Failed to boot the board")


boot_actions = {"board_boot": boot_board}


def post_boot_board(config, env_helper, devices):

    for _ in range(10):
        time.sleep(30)
        if devices.board.is_online():
            break
    else:
        raise BootFail("Board not online.")

    if not devices.board.finalize_boot():
        BootFail("Failed to finalize board.")

    if hasattr(devices.board, "post_boot_init"):
        devices.board.post_boot_init()
    board_uptime = devices.board.hw.consoles[0].get_seconds_uptime()
    logger.info(f"Time up: {board_uptime}")
    if hasattr(devices.board, "__reset__timestamp"):
        time_elapsed = time.time() - devices.board.__reset__timestamp
        logger.info(f"Time since reboot: {time_elapsed}")
        if time_elapsed < board_uptime:
            # TODO: the following should be an exception and not
            # just a print!!!!
            logger.warning("Error: possibly the board did not reset!")
        if (time_elapsed - board_uptime) > 60:
            logger.warning(
                colored(
                    "Board may have rebooted multiple times after flashing process",
                    color="yellow",
                    attrs=["bold"],
                )
            )


def post_boot_wan_clients(config, env_helper, devices):
    pass


def post_boot_lan_clients(config, env_helper, devices):
    for i, v in enumerate(devices.board.dev.lan_clients):
        if getattr(env_helper, "has_lan_advertise_identity", None):
            for option in ["125", "17"]:
                if env_helper.has_lan_advertise_identity(i):
                    v.configure_dhclient(([option, True],))
                else:
                    v.configure_dhclient(([option, False],))
    if config.setup_device_networking:
        for x in devices.board.dev.lan_clients:
            if isinstance(x, DebianLAN):  # should this use devices.lan_clients?
                logger.info(f"Starting LAN client on {x.name}")
                for n in range(3):
                    try:
                        x.configure_docker_iface()
                        if env_helper.get_prov_mode() == "ipv6":
                            x.start_ipv6_lan_client(wan_gw=devices.wan.gw)
                            if env_helper.is_dslite_enabled():
                                x.start_ipv4_lan_client(wan_gw=devices.wan.gw)
                        elif env_helper.get_prov_mode() == "dual":
                            x.start_ipv6_lan_client(wan_gw=devices.wan.gw)
                            x.start_ipv4_lan_client(wan_gw=devices.wan.gw)
                        else:
                            x.start_ipv4_lan_client(wan_gw=devices.wan.gw)
                        x.configure_proxy_pkgs()
                        break
                    except Exception as e:
                        logger.warning(e)
                        logger.error(
                            colored(
                                f"Failed to start lan client on '{x.name}' device, attempt #{n}",
                                color="red",
                                attrs=["bold"],
                            )
                        )
                        time.sleep(10)
                else:
                    msg = f"Failed to start lan client on {x.name}"
                    logger.warning(colored(msg, color="yellow", attrs=["bold"]))
                    # do not fail the boot with raise BootFail(msg)
                    # reason: the board config may be such that the
                    # clients are not getting an ip (see LLCs)


def post_boot_wlan_clients(config, env_helper, devices):
    wifi_clients = env_helper.wifi_clients()
    if wifi_clients:

        # Register all wifi clients in wifi manager
        for client in wifi_clients:
            devices.wlan_clients.register(client)

        # Start to connect all clients after registartions done:
        for client in wifi_clients:
            check_and_connect_to_wifi(devices, client)

        logger.info(colored("\nWlan clients:", color="green"))
        devices.wlan_clients.registered_clients_summary()


def post_boot_env(config, env_helper, devices):
    tr069provision = env_helper.get_tr069_provisioning()
    for _ in range(20):
        try:
            devices.board.get_cpeid()
            break
        except Exception as e:
            logger.error(e)
            warnings.warn("Failed to connect to ACS, retrying")
            time.sleep(10)
    else:
        raise BootFail("Failed to connect to ACS")
    if tr069provision:
        reset_val = any(
            x in env_helper.get_software()
            for x in [
                "factory_reset",
                "pre_flash_factory_reset",
            ]
        )
        if reset_val:
            for i in tr069provision:
                for acs_api in i:
                    API_func = getattr(devices.acs_server, acs_api)
                    for param in i[acs_api]:
                        retry_on_exception(API_func, (param,), tout=60)
        else:
            raise BootFail(
                "Factory reset has to performed for tr069 provisioning. Env json with factory reset true should be used."
            )

    if env_helper.voice_enabled():
        devices.board.sw.voice.configure_voice(
            {"1": devices.fxs1.own_number, "2": devices.fxs2.own_number},
            "1234",
            devices.sipcenter.dns.url,
        )
        for fxs in devices.get_device_array("FXS"):
            if devices.sipcenter.fxs_endpoint_transport == "ipv6":
                fxs.gw = devices.board.get_interface_ip6addr(devices.board.mta_iface)
            else:
                fxs.gw = devices.board.get_interface_ipaddr(devices.board.mta_iface)
    if hasattr(devices.board, "post_boot_env"):
        devices.board.post_boot_env()


post_boot_actions = {
    "board_post_boot": post_boot_board,
    "wan_clients_post_boot": post_boot_wan_clients,
    "lan_clients_post_boot": post_boot_lan_clients,
    "environment_post_boot": post_boot_env,
    "wlan_clients_connection": post_boot_wlan_clients,
}


def run_actions(actions_dict, actions_name, *args, **kwargs):
    logger.info(colored(f"{actions_name} ACTIONS", color="green", attrs=["bold"]))
    for key, func in actions_dict.items():
        try:
            logger.info(colored(f"Action {key} start", color="green", attrs=["bold"]))
            start_time = time.time()
            func(*args, **kwargs)
            logger.info(
                colored(
                    f"\nAction {key} completed. Took {int(time.time() - start_time)} seconds to complete.",
                    color="green",
                    attrs=["bold"],
                )
            )
        except Exception as e:
            msg = f"\nFailed at: {actions_name}: {key} after {int(time.time() - start_time)} seconds with exception {e}"
            logger.error(colored(msg, color="red", attrs=["bold"]))
            raise e
    logger.info(colored(f"{actions_name} COMPLETED", color="green", attrs=["bold"]))


def boot(config, env_helper, devices, logged=None, actions_list=None):
    start_time = time.time()
    if not actions_list:
        actions_list = ["pre", "boot", "post"]
    try:
        if "pre" in actions_list:
            run_actions(pre_boot_actions, "PRE-BOOT", config, env_helper, devices)
        if "boot" in actions_list:
            run_actions(boot_actions, "BOOT", config, env_helper, devices)
        if "post" in actions_list:
            run_actions(post_boot_actions, "POST-BOOT", config, env_helper, devices)
        logger.info(
            colored(
                f"Boot completed in {int(time.time() - start_time)} seconds.",
                color="green",
                attrs=["bold"],
            )
        )
    except Exception:
        traceback.print_exc()
        check_devices(devices)
        logger.info(
            colored(
                f"Boot failed after {int(time.time() - start_time)} seconds.",
                color="red",
                attrs=["bold"],
            )
        )
        raise
