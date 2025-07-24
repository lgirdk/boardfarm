import logging
from typing import Any, Dict, List, Optional, Union

from boardfarm.exceptions import BftEnvExcKeyError, BftEnvMismatch

logger = logging.getLogger("bft")


class EnvHelper:
    """
    Example env json.

    {
        "environment_def": {
            "board": {
                "software": {
                    "bootloader_image": "none",
                    "downgrade_images": [
                        "image.bin"
                    ],
                    "load_image": "image.bin",
                    "upgrade_images": [
                        "image.bin"]
                },
                }
        },
        "version": "1.0"
    }
    """

    def __init__(self, env, mirror=None):
        """Instance initialization."""
        if env is None:
            return

        assert env["version"] in [
            "1.0",
            "1.1",
            "1.2",
            "2.0",
            "2.1",
            "2.2",
            "2.3",
            "2.4",
            "2.5",
            "2.6",
            "2.7",
            "2.8",
            "2.9",
            "2.10",
            "2.11",
            "2.12",
            "2.13",
            "2.14",
            "2.15",
            "2.16",
            "2.17",
            "2.18",
            "2.19",
            "2.20",
            "2.21",
            "2.22",
            "2.23",
            "2.24",
            "2.25",
            "2.26",
            "2.27",
            "2.28",
            "2.29",
            "2.30",
            "2.31",
            "2.32",
            "2.33",
            "2.34",
            "2.35",
            "2.36",
            "2.37",
            "2.38",
            "2.39",
            "2.40",
            "2.41",
            "2.42",
            "2.43",
            "2.44",
            "2.45",
            "2.46",
            "2.47",
            "2.48",
            "2.49",
            "2.50",
        ], "Unknown environment version!"
        self.env = env
        self.mirror = ""
        if mirror:
            self.mirror = mirror

    def get_image(self, mirror=True):
        """Get image.

        returns the desired image for this to run against concatenated with the
        site mirror for automated flashing without passing args to bft
        """
        try:
            if mirror:
                return (
                    self.mirror
                    + self.env["environment_def"]["board"]["software"]["load_image"]
                )
            else:
                return self.env["environment_def"]["board"]["software"]["load_image"]
        except (KeyError, AttributeError):
            return self.get_image_uri(mirror=mirror)

    def get_image_uri(self, mirror=True):
        """Get image URI.

        returns the desired image for this to run against concatenated with the
        site mirror for automated flashing without passing args to bft
        """
        try:
            if mirror:
                return (
                    self.mirror
                    + self.env["environment_def"]["board"]["software"]["image_uri"]
                )
            else:
                return self.env["environment_def"]["board"]["software"]["image_uri"]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_prov_mode(self):
        """
        returns the provisioning mode of the desired environment.
        possible values are: ipv4, ipv6, dslite, dualstack, disabled
        """
        pass

    def has_prov_mode(self):
        """
        returns true or false depending if the environment has specified a
        provisioning mode
        """
        try:
            self.get_prov_mode()
            return True
        except (KeyError, AttributeError):
            return False

    def has_tr069(self) -> bool:
        """
        returns true or false depending if the environment has the tr-069 entry.
        """
        try:
            self.env["environment_def"]["tr-069"]
            return True
        except (KeyError, AttributeError):
            return False

    def has_image(self):
        """Return true or false if the env has specified an image to load."""
        try:
            self.get_image()
            return True
        except Exception:
            return False

    def get_downgrade_image(self):
        """Return the desired downgrade image to test against."""
        try:
            return self.env["environment_def"]["board"]["software"]["downgrade_images"][
                0
            ]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_upgrade_image(self):
        """Return the desired upgrade image to test against."""
        try:
            return self.env["environment_def"]["board"]["software"]["upgrade_images"][0]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def has_upgrade_image(self):
        """Return true or false.

        if the env has specified an upgrade image to load
        """
        try:
            self.get_upgrade_image()
            return True
        except Exception:
            return False

    def has_downgrade_image(self):
        """Return true or false.

        if the env has specified an downgrade image to load
        """
        try:
            self.get_downgrade_image()
            return True
        except Exception:
            return False

    def get_software(self):
        """Get software."""
        sw = self.env["environment_def"]["board"].get("software", {})
        out = {}
        for k, v in sw.items():
            if k == "dependent_software":
                continue
            if k in ["load_image", "image_uri"]:
                out[k] = f"{self.mirror}{v}"
            else:
                out[k] = v
        return out

    def get_dependent_software(self):
        """Get dependent software."""
        d = self.env["environment_def"]["board"].get("software", {})
        sw = d.get("dependent_software", {})
        out = {}
        for k, v in sw.items():
            if k in ["load_image", "image_uri"]:
                out[k] = f"{self.mirror}{v}"
            else:
                out[k] = v
        return out

    def get_flash_strategy(self):
        """Get software flash strategy."""
        sw = self.env["environment_def"]["board"].get("software", {})
        out = {}
        for k, v in sw.items():
            if k == "dependent_software":
                continue
            if k == "flash_strategy":
                out[k] = f"{v}"
        return out

    def get_board_hardware_type(self):
        """Returns board hardware type according to
        ["environment_def"]["board"]["model"]
        :return: mv1/mv2/mv2+/mv3 etc. or unknown if not found in mapping
        """
        board_model = self.get_board_model()
        return {
            "F3896LG": "mv2+",
            "CH7465LG": "mv1",
            "TG2492LG": "mv1",
            "F5685LGE": "mv3",
            "F5685LGB": "mv3",
        }.get(board_model, "unknown")

    def env_check(self, test_environment):
        """Test environment check.

        Given an environment (in for of a dictionary) as a parameter, checks
        if it is a subset of the environment specs contained by the EnvHelper.

        :param test_environment: the environment to be checked against the EnvHelper environment
        :type test_environment: dict

        .. note:: raises BftEnvMismatch  if the test_environment is not contained in the env helper environment
        .. note:: recursively checks dictionaries
        .. note:: A value of None in the test_environment is used as a wildcard, i.e. matches any values int the EnvHelper
        """

        def contained(env_test, env_helper, path="root"):
            if type(env_test) is dict:
                for k in env_test:
                    if k not in env_helper or not contained(
                        env_test[k], env_helper[k], path + "->" + k
                    ):
                        return False
            elif type(env_test) is list:
                # Handle case where env_test is a list and the env_helper is a value:
                # e.g. the env helper is configured in mode A
                # the test can run in A, B or C configuration modes
                if not type(env_helper) is list:
                    return env_helper in env_test
                # Handle case where list is [None] and we just need *some value* in the env_helper
                if env_test[0] is None and len(env_helper) > 0:
                    return True

                if type(env_helper) is list:
                    # Validate list of dictionary or list of string
                    env_helper_list = env_helper.copy()
                    count = 0
                    for test in env_test:
                        if not type(test) is dict:
                            if test not in env_helper_list:
                                return False
                            count += 1
                        else:
                            for env in env_helper_list:
                                if "SPV" in env:
                                    test_list = test.get("SPV", [])
                                    env_list = env.get("SPV", [])
                                    if any(i in env_list for i in test_list):
                                        env_helper_list.remove(env)
                                        count += 1
                                        break
                                if test.items() <= env.items():
                                    env_helper_list.remove(env)
                                    count += 1
                                    break
                    if len(env_test) != count:
                        return False
            else:
                if env_test is None and env_helper is not None:
                    return True
                elif env_test == env_helper:
                    return True
                else:
                    return False

            return True

        if not contained(test_environment, self.env):
            logger.error("---------------------")
            logger.error(" test case env: ")
            logger.error(test_environment)
            logger.error(" env_helper   : ")
            logger.error(self.env)
            logger.error("---------------------")
            raise BftEnvMismatch()

        return True

    @staticmethod
    def env_devices(env_json):
        devices = {}

        # find all possible devices.
        # Selection criteria: they have a "device_type" key.
        # They're always found inside a list
        def find_device_arrays(env):
            nonlocal devices
            for k, v in env.items():
                if type(v) == dict:
                    if "device_type" in v:
                        devices[k] = [v]
                    find_device_arrays(v)
                if type(v) == list and all(
                    type(obj) == dict and "device_type" in obj for obj in v
                ):
                    devices[k] = v

        find_device_arrays(env_json)
        return devices

    def get_update_image(self, mirror=True):
        """Get the image update uri.

        returns the desired image to be updated for this to run against concatenated with the
        site mirror for software upgrade/downgrade test
        """
        try:
            if mirror:
                return (
                    self.mirror
                    + self.env["environment_def"]["board"]["software_update"][
                        "load_image"
                    ]
                )
            else:
                return self.env["environment_def"]["board"]["software_update"][
                    "load_image"
                ]
        except (KeyError, AttributeError):
            return self.get_update_image_uri(mirror=mirror)

    def get_update_image_uri(self, mirror=True):
        """Get the image update uri.

        returns the desired image to be updated for this to run against concatenated with the
        site mirror for software upgrade/downgrade test
        """
        try:
            if mirror:
                return (
                    self.mirror
                    + self.env["environment_def"]["board"]["software_update"][
                        "image_uri"
                    ]
                )
            else:
                return self.env["environment_def"]["board"]["software_update"][
                    "image_uri"
                ]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_update_image_version(self):
        """Get the image version name from env for software update.

        returns the image version name for software update uniquely defined for an image
        """
        try:
            return self.env["environment_def"]["board"]["software_update"][
                "image_version"
            ]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_alternative_image(self, mirror=True):
        """Get the alternative image uri.

        returns the alternative image to be updated for this to run against concatenated with the
        site mirror for software upgrade/downgrade test
        """
        try:
            if mirror:
                return (
                    self.mirror
                    + self.env["environment_def"]["board"]["software_alternative"][
                        "load_image"
                    ]
                )
            else:
                return self.env["environment_def"]["board"]["software_alternative"][
                    "load_image"
                ]
        except (KeyError, AttributeError):
            return self.get_alternative_image_uri(mirror=mirror)

    def get_alternative_image_uri(self, mirror=True):
        """Get the alternative image uri.

        returns the alternative image to be updated for this to run against concatenated with the
        site mirror for software upgrade/downgrade test
        """
        try:
            if mirror:
                return (
                    self.mirror
                    + self.env["environment_def"]["board"]["software_alternative"][
                        "image_uri"
                    ]
                )
            else:
                return self.env["environment_def"]["board"]["software_alternative"][
                    "image_uri"
                ]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_alternative_image_version(self):
        """Get the alternative image version name from env for software update.

        returns the alternative image version name for software update uniquely defined for an image
        """
        try:
            return self.env["environment_def"]["board"]["software_alternative"][
                "image_version"
            ]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_ertr_mode(self):
        return {"max_config": True}

    def get_country(self):
        """This method returns the country name from env json.

        :return: possible values are NL,AT,CH,CZ,DE,HU,IE,PL,RO,SK
        :rtype: string
        """
        try:
            return self.env["environment_def"]["board"]["country"]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def voice_enabled(self):
        """This method returns true if voice is enabled in env JSON.

        :return: possible values are True/False
        :rtype: boolean
        """
        try:
            return "voice" in self.env["environment_def"]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def wifi_clients(self) -> list:
        """Returns list of wifi clients from environment definition

        :rtype: list
        """
        try:
            clients = self.env["environment_def"]["board"]["wifi_clients"]
        except (KeyError, AttributeError):
            return list()
        return clients

    def has_lan_advertise_identity(self, idx):
        """Return lan identity value defined in lan_clients of env else return False.

        :idx: lan client index from lan_clients to return corresponding value
        :type: integer

        :return: possible values are True/False
        :rtype: boolean
        """

        try:
            return self.env["environment_def"]["board"]["lan_clients"][idx][
                "advertise_identity"
            ]
        except (IndexError, KeyError, AttributeError):
            return False

    def get_mitm_devices(self):
        """
        returns list of mitm'ed devices of the desired environment.
        """
        try:
            devices = self.env["environment_def"]["mitm"]
        except (KeyError, AttributeError):
            return list()
        return devices

    def mitm_enabled(self):
        """Flag to see if we have any devices mitm'ed

        :return: True if at least 1 device mitm'ed, False otherwise
        """
        return bool(self.get_mitm_devices())

    def get_tr069_provisioning(self):
        """Return list of ACS APIs to be executed during tr069 provisioning.

        :return: object containing list ACS APIs to call for provisioning
        :rtype: dictionary
        """

        try:
            return self.env["environment_def"]["tr-069"]["provisioning"]
        except (KeyError, AttributeError):
            return False

    def get_dns_dict(self):
        """Returns the dict of reachable and unreachable IP address from DNS.

        :return: number of reachable and unreachable IP address to be fetched from DNS
        :rtype: dictionary
        """
        try:
            return self.env["environment_def"]["DNS"]
        except (KeyError, AttributeError):
            return False

    def get_board_sku(self):
        """Returns the ["environment_def"]["board"]["SKU"] value
        :return: SKU values from eval list
        :rtype: String"""

        try:
            return self.env["environment_def"]["board"]["SKU"]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def has_board_sku(self):
        """Returns True if  ["environment_def"]["board"]["SKU"] exists
        :return: possible values are True/False
        :rtype: bool"""
        try:
            self.get_board_sku()
            return True
        except BftEnvExcKeyError:
            return False

    def get_board_gui_language(self):
        """Returns the ["environment_def"]["board"]["GUI_Language"] value
        :return: GUI_Language values from eval list
        :rtype: String"""

        try:
            return self.env["environment_def"]["board"]["GUI_Language"]
        except (KeyError, AttributeError) as GUILangError:
            raise BftEnvExcKeyError from GUILangError

    def has_board_gui_language(self):
        """Returns True if  ["environment_def"]["board"]["GUI_Language"] exists
        :return: possible values are True/False
        :rtype: bool"""
        try:
            self.get_board_gui_language()
            return True
        except BftEnvExcKeyError:
            return False

    def is_production_image(self):
        return (
            self.env["environment_def"]["board"]["software"]["image_uri"].find("NOSH")
            != -1
        )

    def dhcp_options(self):
        """Returns the ["environment_def"]["provisioner"]["options"].

        :return:  return list of DHCPv4 and DHCPv6 option
        :rtype: dict
        """
        try:
            return self.env["environment_def"]["provisioner"]["dhcp_options"]
        except (KeyError, AttributeError):
            return dict()

    def vendor_encap_opts(self, ip_proto=None):
        """Check vendor specific option for ACS URL is specified in env

        :return: return True if dhcp option for acs url is configured
        :rtype: bool
        """
        dhcp_options = self.dhcp_options()
        if ip_proto == "ipv4" and 125 in dhcp_options.get("dhcpv4", []):
            return True
        elif ip_proto == "ipv6" and 17 in dhcp_options.get("dhcpv6", []):
            return True
        return False

    def get_board_boot_file_mta(self):
        """Returns the ["environment_def"]["board"]["emta"]["boot_file_mta"] value
        :return: the emta boot file value as a string
        :rtype: String"""
        try:
            return self.env["environment_def"]["board"]["emta"]["boot_file_mta"]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def has_board_boot_file_mta(self):
        """Returns True if  ["environment_def"]["board"]["emta"]["boot_file_mta"] exists
        :return: possible values are True/False
        :rtype: bool"""
        try:
            self.get_board_boot_file_mta()
            return True
        except BftEnvExcKeyError:
            return False

    def get_external_voip(self):
        """Return the ["environment_def"]["voice"]["EXT_VOIP"] value

        :return: External VoIP entries
        :rtype: list
        """
        try:
            return self.env["environment_def"]["voice"]["EXT_VOIP"]
        except (KeyError, AttributeError):
            return False

    def get_cwmp_version(self):
        """Return the ["environment_def"]["board"]["cwmp_version"]

        :return: CWMP version of DUT
        :rtype: str
        """
        try:
            return self.env["environment_def"]["board"]["cwmp_version"]
        except (KeyError, AttributeError):
            return False

    def get_board_model(self) -> str:
        """Return the ["environment_def"]["board"]["model"]

        :return: Board model
        """
        try:
            return self.env["environment_def"]["board"]["model"]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError("Unable to find board.model entry in env.")

    def get_provisioner_options(
        self,
    ) -> Dict[Optional[str], Optional[Union[str, int]]]:
        """Return Dict of options on provisioner from environment definition

        :return: List of dhcpv4 options
        :rtype: Dict[Optional[str], Optional[Union[str, int]]]
        """
        return (
            self.env.get("environment_def", {})
            .get("provisioner", {})
            .get("dhcp_options", {})
        )

    def is_route_gateway_valid(self) -> bool:
        """check if valid dhcp gateways ip configurations should be deployed

        :return: return True if dhcp option route_gateway is valid else False
        :rtype: bool
        """
        return self.get_provisioner_options().get("route_gateway", None) != "invalid"

    def get_mta_config(self):
        """Returns the ["environment_def"]["voice"]["mta_config_boot"]["snmp_mibs"] values
        :return: the vendor specific mta dict
        :rtype: list, bool if Key/Attribure Error"""

        try:
            return self.env["environment_def"]["voice"]["mta_config_boot"]["snmp_mibs"]
        except (KeyError, AttributeError):
            return False

    def get_emta_config_template(self):
        """Return the ["environment_def"]["board"]["emta"]["config_template"] value
        :return: emta config template ex: "CH_Compal"
        :rtype: string
        """
        try:
            return self.env["environment_def"]["board"]["emta"]["config_template"]
        except (KeyError, AttributeError):
            return False

    def get_emta_interface_status(self):
        """Return the ["environment_def"]["board"]["emta"]["interface_status"] value
        :return: emta interface status ex: "down"
        :rtype: string
        """
        try:
            return self.env["environment_def"]["board"]["emta"]["interface_status"]
        except (KeyError, AttributeError):
            return False

    def get_lan_client_options(self) -> List[Dict]:
        """get lan client options

        :return: client options for all lan client
        :rtype: dict
        """
        return (
            self.env.get("environment_def", {}).get("board", {}).get("lan_clients", {})
        )

    def is_set_static_ipv4(self, idx) -> bool:
        """check if static ipv4 assignment is enabled

        :return: return True if dhcpv4 option static_ipv4 is true else False
        :rtype: bool
        """
        try:
            return self.get_lan_client_options()[idx].get("static_ipv4")
        except (IndexError, KeyError, AttributeError):
            return False

    def get_value(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the value of the key provided.

        :return: The value of the key provided
        :rtype: Union[Dict[str,Any], bool]
        """
        try:
            return self.env["environment_def"][key]
        except (KeyError, AttributeError):
            return None
