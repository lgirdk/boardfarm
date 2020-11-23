import json
from collections import UserList

from boardfarm.exceptions import CodeError
from boardfarm.lib.wrappers import singleton


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
        self.private = []
        self.guest = []
        self.community = []

        # used to pop elements from one bucket to another.
        self.__available = {2.4: [], 5: []}

        self.__used = {2.4: [], 5: []}

    def register(self, wlan_options: dict):
        dev = None

        # try 1: get device via band
        if "band" in wlan_options:
            band = wlan_options["band"]
            if self.__available[band]:
                dev = self.__available[band].pop(0)
                self.__used[band].append(dev)

        # try 2: select first available device from in-built list
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
        nw_bucket = getattr(self, wlan_options["network"].lower())
        nw_bucket.append(dev)

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
            nw_bucket = getattr(self, network.lower())
            result.append(nw_bucket)
        if band:
            result.append(self.__used[band])

        return list(set.intersection(*map(set, result)))
