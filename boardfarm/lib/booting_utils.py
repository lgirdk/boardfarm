"""
Utils file for functions that are used in booting process.
Created in order to keep booting.py implementation as clean as possible
"""
import time

from loguru import logger


def check_and_connect_to_wifi(devices, wifi_client_data: dict) -> None:
    """Check if specific wifi is enabled and try to connect appropriate client

    :param devices: device manager
    :param wifi_client_data: wifi client config dict from envvironment definition
    """

    wifi = devices.board.wifi
    # Get desired wlan details from env definition
    band = wifi_client_data.get("band")
    network = wifi_client_data.get("network")
    protocol = wifi_client_data.get("protocol")
    authentication = wifi_client_data.get("authentication")

    # Check if all necessary data is provided
    if not all([band, network, protocol, authentication]):
        logger.error(
            f"Unable to get all client details from environment definition: {wifi_client_data}"
            "Please check that band, network, protocol and authentication keys are present"
        )
        return

    # Enable desired wifi if not enabled yet.
    wifi_dmcli_id = wifi.dmcli_wifi_mapping[network][band]
    radio_dmcli_id = wifi.dmcli_radio_mapping[band]
    if not wifi.console.is_wifi_enabled(network, band):
        logger.info(f"{band} GHz {network} network is not enabled. Enabling...")
        wifi.hal.hal_wifi_setApEnable(wifi_dmcli_id, "true")
        wifi.hal.hal_wifi_applysetting(radio_dmcli_id)
        # Wait for wifi init complete after dmcli. 3 retires with 30 seconds delay.
        for _ in range(1, 4):
            time.sleep(30)
            if wifi.console.is_wifi_enabled(network, band):
                break
        else:
            logger.error(f"Failed to enable {band} GHz {network} network. Skipping")
            return

    # Obtain network connection details. 3 retries with 30 seconds delay
    ssid = None
    bssid = None
    password = None
    for idx in range(1, 4):
        logger.info(
            f"Trying to get {band} GHz {network} network connection details. Try #{idx}"
        )
        ssid = getattr(wifi.console, f"{network}_ssid")(band)
        bssid = getattr(wifi.console, f"{network}_bssid")(band)
        password = getattr(wifi.console, f"{network}_passphrase")()
        if all([ssid, bssid, password]):
            break
        time.sleep(30)
    else:
        logger.error(
            f"Unable to get {band} GHz {network} network connection details. Skipping"
        )
        return

    # Connect appropriate client to the network
    if wifi_client_data.get("connect_wifi"):
        try:
            wlan_client = devices.wlan_clients.filter(network, band)[0]
            wlan_client.wifi_client_connect(
                ssid_name=ssid,
                password=password,
                bssid=bssid,
                security_mode=authentication,
            )
            wlan_client.configure_proxy_pkgs()

        except AssertionError as e:
            logger.exception(
                f"Unable to connect to {band} GHz {network} network: connection error"
            )
            raise AssertionError from e
