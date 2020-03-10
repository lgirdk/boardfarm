import json
import os
import re

import boardfarm
import six
from boardfarm.dbclients.boardfarmwebclient import BoardfarmWebClient
from boardfarm.lib.common import print_bold


def get_station_config(location=None):
    '''
    A "station config" describes what things are available to connect to
    for testing. The format of this config should be JSON.
    Here we read that configuration and add/remove some information.
    '''
    boardfarm_config = read_station_config(location)
    if "_redirect" in boardfarm_config:
        print("Using boardfarm config file at %s" %
              boardfarm_config['_redirect'])
        print("Please set your default config by doing:")
        print('    export BFT_CONFIG="%s"' % boardfarm_config['_redirect'])
        print("If you want to use local config, remove the _redirect line.")
        location = boardfarm_config['_redirect']
        boardfarm_config = read_station_config(boardfarm_config['_redirect'])
        boardfarm_config.pop('_redirect', None)
    return location, process_station_config(boardfarm_config)


def read_station_config(location):
    '''
    Given a location (ether "http://..." or file path) for a config file
    of boardfarm stations, read it, and process it as JSON.
    '''
    if location.startswith("http"):
        data = BoardfarmWebClient(location,
                                  bf_version=boardfarm.__version__,
                                  debug=os.environ.get("BFT_DEBUG",
                                                       False)).bf_config_str
    else:
        data = open(location, 'r').read()

    return json.loads(data)


def process_station_config(boardfarm_config):
    '''
    Add location-specific data to boardfarm stations.
    '''

    if 'locations' in boardfarm_config:
        location = boardfarm_config['locations']
        del boardfarm_config['locations']

        for board in boardfarm_config:
            if 'location' in boardfarm_config[board]:
                board_location = boardfarm_config[board]['location']
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
        s += "%s : %s\n" % (k, v)

    if all(re.findall(f, s) for f in filter):
        if name:
            print("matched %s on %s, adding %s" % (filter, board_config, name))
        return True
    return False


def filter_station_config(boardfarm_config,
                          board_type=None,
                          board_names=[],
                          board_features=[],
                          board_filter=None):
    '''
    From the boardfarm config, return a list of board names that
    match filter criteria.
    '''
    result = []

    if board_type:
        print_bold("Selecting board from board type = %s" % board_type)
        possible_names = boardfarm_config
        if board_names:
            print("Board names = %s" % board_names)
            # Allow selection only from given set of board names
            possible_names = set(boardfarm_config) & set(board_names)
        for b in possible_names:
            if len(board_names) != 1 and \
               'available_for_autotests' in boardfarm_config[b] and \
               boardfarm_config[b]['available_for_autotests'] == False:
                # Skip this board
                continue
            if board_features != []:
                if 'feature' not in boardfarm_config[b]:
                    continue
                features = boardfarm_config[b]['feature']
                if 'devices' in boardfarm_config[b]:
                    seen_names = []
                    for d in boardfarm_config[b]['devices']:
                        if 'feature' in d:
                            # since we only connect to one type of device
                            # we need to ignore the features on the other ones
                            # even though they should be the same
                            if d['name'] in seen_names:
                                continue
                            seen_names.append(d['name'])

                            if type(d['feature']) in (str, six.text_type):
                                d['feature'] = [d['feature']]
                            features.extend(x for x in d['feature']
                                            if x not in features)
                if type(features) in (str, six.text_type):
                    features = [features]
                if set(board_features) != set(board_features) & set(features):
                    continue
            for t in board_type:
                if boardfarm_config[b]['board_type'].lower() == t.lower():
                    if board_filter:
                        if filter_boards(boardfarm_config[b], board_filter, b):
                            result.append(b)
                    else:
                        result.append(b)
    else:
        if board_names:
            result = board_names

    return result
