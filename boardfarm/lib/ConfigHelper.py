import traceback
from boardfarm.exceptions import ConfigKeyError


class ConfigHelper(dict):
    '''
    Accessing the board (station) configuration will soon go through this class.

    Getters and Setters will be here, rather than accessing the dict directly
    so that some control can be maintained.
    '''
    def __init__(self, *args, **kwargs):
        self.update(*args, **kwargs)

    def __getitem__(self, key):
        if key == 'mirror':
            print('WARNING ' * 9)
            print(
                'Support for calling config["mirror"] directly is going to be removed.'
            )
            print(
                'Please change your test as soon as possible to this file transfer'
            )
            print('in the proper way.')
            print('WARNING ' * 9)

        if key in ('cm_cfg', 'mta_cfg', 'erouter_cfg'):
            print(
                "ERROR: use of cm_cfg or mta_cfg in config object is deprecated!"
            )
            print("Use board.cm_cfg or board.mta_cfg directly!")
            traceback.print_exc()
            raise ConfigKeyError

        if key in ('station'):
            print("ERROR: use get_station() not ['station']")
            traceback.print_exc()
            raise ConfigKeyError

        return dict.__getitem__(self, key)

    def get_station(self):
        return dict.__getitem__(self, 'station')
