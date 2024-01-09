import json
import logging
from collections import UserList

from tabulate import tabulate
from termcolor import colored

from boardfarm.exceptions import CodeError
from boardfarm.lib.wrappers import singleton

logger = logging.getLogger("bft")


@singleton
class WiFiMgr(UserList):
    """Device Manager for Wi-Fi clients

    Object will get attached to main DeviceManger module
    as an attribute wlan_devices.

    Idea is to have a filter methods added to the list for ease of
    selecting Wi-Fi client based on the band and network type.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Network type buckets
        self.private = []
        self.guest = []
        self.community = []

        # Band buckets
        self.__available = {"2.4": [], "5": [], "dual": []}
        self.__used = {"2.4": [], "5": [], "dual": []}

    def register(self, wlan_options: dict):
        dev = None

        # try 1: get device via band
        if "band" in wlan_options:
            band = wlan_options["band"]
            if self.__available[band]:
                dev = self.__available[band].pop(0)
                self.__used[band].append(dev)
            # try 2: grab dual-band device if available
            elif self.__available["dual"]:
                dev = self.__available["dual"].pop(0)
                logger.warning(
                    colored(
                        f"{band} GHz single-band device was not found. Registering dual-band {dev.name} as {band} GHz",
                        color="yellow",
                        attrs=["bold"],
                    )
                )
                self.__used[band].append(dev)

        # try 3: select first available device from in-built list
        else:
            for dev in self.data:
                if self.is_available(dev):
                    band = dev.band
                    self.__available[band].pop(dev)
                    self.__used[band].append(dev)
                    break

        # if dev is still None, raise CodeError
        if not dev:
            raise CodeError(
                f"No Wi-Fi Device available for below JSON: \n{json.dumps(wlan_options, indent=4)}"
            )

        # WLAN_OPTIONS must specify network type
        if wlan_options["connect_wifi"] is True:
            network_type_bucket = getattr(self, wlan_options["network"].lower())
            network_type_bucket.append(dev)

        # set authentication type, by default NONE
        if "authentication" in wlan_options:
            dev.set_authentication(wlan_options["authentication"])

    def append(self, dev: object):
        # add any new device into respective avaiable bucket
        try:
            band = dev.band
            self.__available[band].append(dev)
            super().append(dev)
        except BaseException as e:
            # this should not happen, only allow Wi-Fi clients to be appended.
            raise CodeError(str(e))

    def is_available(self, dev: object):
        for bucket in self.__available.values():
            if dev in bucket:
                return True
        return False

    def filter(self, network: str = None, band: float = None):
        """Return list of wlan_devices based on filter."""
        if not network and not band:
            raise CodeError("Invalid filter!!")

        result = []
        if network:
            network_type_bucket = getattr(self, network.lower())
            result.append(network_type_bucket)
        if band:
            result.append(self.__used[band])

        return list(set.intersection(*map(set, result)))

    def registered_clients_summary(self):
        """Print a table to a log with registered clients summary
        Example:
          ╒═════════════════════╤═════════════════╤════════════════╕
          │ Client name(band)   │   Assigned band │ Network type   │
          ╞═════════════════════╪═════════════════╪════════════════╡
          │ wlan4(2.4)          │             2.4 │ private        │
          ├─────────────────────┼─────────────────┼────────────────┤
          │ wlan1(dual)         │             2.4 │ guest          │
          ├─────────────────────┼─────────────────┼────────────────┤
          │ wlan3(5)            │             5   │ private        │
          ╘═════════════════════╧═════════════════╧════════════════╛
        """
        table = []
        for band, devices in self.__used.items():
            for device in devices:
                row = []
                row.append(f"{device.name}({device.band})")
                row.append(band)
                if device in self.private:
                    row.append("private")
                else:  # No community networks for now
                    row.append("guest")
                table.append(row)
        logger.info(
            colored(
                tabulate(
                    sorted(table, key=lambda a: a[0]),  # Sort by device name
                    headers=["Client name(band)", "Assigned band", "Network type"],
                    tablefmt="fancy_grid",
                ),
                color="green",
            )
        )
