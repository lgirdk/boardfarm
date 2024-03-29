import json
import logging
import os
import re

import httpx
import six

import boardfarm
from boardfarm.dbclients.boardfarmwebclient import BoardfarmWebClient
from boardfarm.lib.common import print_bold

logger = logging.getLogger("bft")


class BoardfarmTestConfig:
    """
    This class defines the location or values of high-level objects
    used to run tests. Such as: url of the inventory server,
    environment files, etc...
    """

    def __init__(self, name="results"):
        self.name = name
        self.output_dir = os.path.join(
            os.path.abspath(os.path.join(os.getcwd(), name, "")), ""
        )
        self.EXTRA_TESTS = []
        self.BOARD_NAMES = []
        self.boardfarm_config_location = None
        self.boardfarm_config = None
        self.UBOOT = None
        self.KERNEL = None
        self.ROOTFS = None
        self.NFSROOT = None
        self.META_BUILD = None
        self.WAN_PROTO = "dhcp"
        self.setup_device_networking = True
        self.bootargs = None
        self.golden = []
        self.golden_master_results = {}
        self.features = []
        self.TEST_SUITE_NOSTRICT = False
        self.regex_config = []
        self.retry = 0
        self.test_args_location = os.environ.get("BFT_ARGS", None)
        self.elasticsearch_server = os.environ.get("BFT_ELASTICSERVER", None)
        self.test_args = None
        self.err_injection_dict = {}
        self.bf_board_name = None
        self.bf_board_type = None
        self.bf_skip_reservation_check = False


def get_station_config(location=None, ignore_redir=False):
    """
    A "station config" describes what things are available to connect to
    for testing. The format of this config should be JSON.
    Here we read that configuration and add/remove some information.
    """
    boardfarm_config = read_station_config(location)
    if "_redirect" in boardfarm_config and not ignore_redir:
        logger.debug(f"Using boardfarm config file at {boardfarm_config['_redirect']}")
        logger.debug("Please set your default config by doing:")
        logger.debug(f"    export BFT_CONFIG=\"{boardfarm_config['_redirect']}\"")
        logger.debug("If you want to use local config, remove the _redirect line.")
        location = boardfarm_config["_redirect"]
        boardfarm_config = read_station_config(boardfarm_config["_redirect"])
        boardfarm_config.pop("_redirect", None)
    return location, process_station_config(boardfarm_config)


def read_station_config(location):
    """
    Get the boards inventory.

    Given a location (ether "http://..." or file path) for a config file
    of boardfarm stations, read it, and process it as JSON.
    """
    if location.startswith("http"):
        _res = httpx.get(
            location,
            auth=tuple(os.environ.get("LDAP_CREDENTIALS").split(";")),
        )
        _res.raise_for_status()
        data = _res.text
    else:
        data = open(location, encoding="utf-8").read()

    return json.loads(data)


def process_station_config(boardfarm_config):
    """
    Add location-specific data to boardfarm stations.
    """

    if "locations" in boardfarm_config:
        location = boardfarm_config["locations"]
        del boardfarm_config["locations"]

        for board in boardfarm_config:
            if "location" in boardfarm_config[board]:
                board_location = boardfarm_config[board]["location"]
                if board_location in location:
                    for key, value in location[board_location].items():
                        if type(value) == list:
                            boardfarm_config[board][key].extend(value)
                        else:
                            boardfarm_config[board][key] = value

    return boardfarm_config


def filter_boards(board_config, filter, name=None):
    """Choose boards based on the filter provided

    :param board_config: board config parameters
    :type board_config: dictionary
    :param filter: filter type for the board
    :type filter: string
    :param name: board name
    :type name: string
    :return: True or False
    :rtype: boolean
    """
    s = ""
    for k, v in board_config.items():
        s += f"{k} : {v}\n"

    if all(re.findall(f, s) for f in filter):
        if name:
            logger.info(f"matched {filter} on {board_config}, adding {name}")
        return True
    return False


def filter_station_config(
    boardfarm_config,
    board_type=None,
    board_names=[],
    board_features=[],
    board_filter=None,
):
    """
    From the boardfarm config, return a list of board names that
    match filter criteria.
    """
    result = []

    if board_type:
        print_bold(f"Selecting board from board type = {board_type}")
        possible_names = boardfarm_config
        if board_names:
            logger.info(f"Board names = {board_names}")
            # Allow selection only from given set of board names
            possible_names = set(boardfarm_config) & set(board_names)
        for b in possible_names:
            if b == "_redirect":
                continue
            if (
                len(board_names) != 1
                and "available_for_autotests" in boardfarm_config[b]
                and boardfarm_config[b]["available_for_autotests"] is False
            ):
                # Skip this board
                continue
            if board_features != []:
                if "feature" not in boardfarm_config[b]:
                    continue
                features = boardfarm_config[b]["feature"]
                if "devices" in boardfarm_config[b]:
                    seen_names = []
                    for d in boardfarm_config[b]["devices"]:
                        if "feature" in d:
                            # since we only connect to one type of device
                            # we need to ignore the features on the other ones
                            # even though they should be the same
                            if d["name"] in seen_names:
                                continue
                            seen_names.append(d["name"])

                            if type(d["feature"]) in (str, str):
                                d["feature"] = [d["feature"]]
                            features.extend(
                                x for x in d["feature"] if x not in features
                            )
                if type(features) in (str, str):
                    features = [features]
                if set(board_features) != set(board_features) & set(features):
                    continue
            for t in board_type:
                __board_type = boardfarm_config[b]["board_type"]
                if type(__board_type) is str:
                    __board_type = [__board_type]
                if t.lower() in (__bt.lower() for __bt in __board_type):
                    boardfarm_config[b]["board_type"] = t
                    if board_filter:
                        if filter_boards(boardfarm_config[b], board_filter, b):
                            result.append(b)
                    else:
                        result.append(b)
    else:
        if board_names:
            result = board_names

    return result
