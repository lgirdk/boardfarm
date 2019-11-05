from . import linux

class OpenEmbedded(linux.LinuxDevice):
    '''OE core implementation'''

    def install_package(self, pkg):
        '''Install packages '''
        raise Exception("Not implemented!")
