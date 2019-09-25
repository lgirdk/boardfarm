from boardfarm.exceptions import BftEnvExcKeyError

class EnvHelper(object):
    '''
    Example env json
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
                        "image.bin"
                },
                }
        },
        "version": "1.0"
    }
    '''

    def __init__(self, env):
        if env is None:
            return

        assert env['version'] == '1.0', "Unknown environment version!"
        self.env = env

    def get_image(self):
        '''
        returns the desired image for this to run against concatenated with the
        site mirror for automated flashing without passing args to bft
        '''
        try:
            from boardfarm import config
            return config.board[u'mirror'] + self.env['environment_def']['board']['software']['load_image']
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def has_image(self):
        '''
        returns true or false if the env has specified an image to load
        '''
        try:
            self.get_image()
            return True
        except:
            return False

    def get_downgrade_image(self):
        '''
        returns the desired downgrade image to test against
        '''
        try:
            return self.env['environment_def']['board']['software']['downgrade_images'][0]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_upgrade_image(self):
        '''
        returns the desired upgrade image to test against
        '''
        try:
            return self.env['environment_def']['board']['software']['upgrade_images'][0]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def has_upgrade_image(self):
        '''
        returns true or false if the env has specified an upgrade image to load
        '''
        try:
            self.get_upgrade_image()
            return True
        except:
            return False


    def has_downgrade_image(self):
        '''
        returns true or false if the env has specified an downgrade image to load
        '''
        try:
            self.get_downgrade_image()
            return True
        except:
            return False
