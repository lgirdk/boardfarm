
import json
import os
import boardfarm
from boardfarm.dbclients.boardfarmwebclient import BoardfarmWebClient


def get_station_config(location):
    '''
    A "station config" describes what things are available to connect to
    for testing. The format of this config should be JSON.
    Here we read that configuration and add/remove some information.
    '''
    boardfarm_config = read_station_config(location)
    return process_station_config(boardfarm_config)


def read_station_config(location):
    '''
    Given a location (ether "http://..." or file path) for a config file
    of boardfarm stations, read it, and process it as JSON.
    '''
    if location.startswith("http"):
        data = BoardfarmWebClient(location,
                                  bf_version=boardfarm.__version__,
                                  debug=os.environ.get("BFT_DEBUG", False)).bf_config_str
    else:
        data = open(location, 'r').read()

    return json.loads(data)


def process_station_config(boardfarm_config):
    '''
    Follow a _redirect if present, and add location-specific data to
    boardfarm stations.
    '''

    if "_redirect" in boardfarm_config:
        print("Using boardfarm config file at %s" % boardfarm_config['_redirect'])
        print("Please set your default config by doing:")
        print('    export BFT_CONFIG="%s"' % boardfarm_config['_redirect'])
        print("If you want to use local config, remove the _redirect line.")
        boardfarm_config = read_station_config(boardfarm_config['_redirect'])
        boardfarm_config.pop('_redirect', None)

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
