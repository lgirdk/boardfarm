import linux, os, re

class OpenEmbedded(linux.LinuxDevice):
    '''OE core implementation'''

    def install_package(self, pkg):
        '''Install packages '''
        raise Exception("Not implemented!")
