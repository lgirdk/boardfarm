

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
            print('WARNING '*9)
            print('Support for calling config["mirror"] directly is going to be removed.')
            print('Please change your test as soon as possible to this file transfer')
            print('in the proper way.')
            print('WARNING '*9)
        return dict.__getitem__(self, key)
