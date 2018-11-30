# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import os, config
from common import cmd_exists

class docsis:
    """
    Name: docsis module
    Purpose: docsis operating.
    Input: Absolute path of text file
    Fuction:
        decode():
            return output file name(.txt)
        encode(output_type='cm_cfg')
            return output file name(.cfg or .bin)
    """
    def __init__(self, file_path, tmpdir=None):
        # TODO: fix at some point, this tmpdir is already relative to the CM config you
        # are grabbing? Not ideal as that dir might not be writeable, or a tftp or http URL
        # at some point - need to use a real local tmpdir or maybe even results so we can
        # save the resulting artifacts in other tools
        if tmpdir is None:
            tmpdir = os.path.join('tmp', config.board['station'])

        self.file_path=file_path
        self.dir_path=os.path.join(os.path.split(file_path)[0], tmpdir)
        self.file=os.path.split(file_path)[1]

        # make target tmpdir if it does not exist
        try:
            os.makedirs(self.dir_path)
        except OSError, err:
            import errno
            # Reraise the error unless it's about an already existing directory
            if err.errno != errno.EEXIST or not os.path.isdir(self.dir_path):
                raise

        assert cmd_exists('docsis')

    def decode(self):
        if '.cfg' in self.file:
            os.system("docsis -d %s > %s" %(self.file_path, self.file_path.replace('.cfg', '.txt')))
            assert os.path.exists(self.file.replace('.cfg', '.txt'))

            return  self.file.replace('.cfg', '.txt')

        # TODO: decode MTA?

    def encode(self, output_type='cm_cfg'):
        def encode_mta():
            mtacfg_name=self.file.replace('.txt', '.bin')
            mtacfg_path=os.path.join(self.dir_path, mtacfg_name)
            cmd = "tclsh %s/mta_conf.tcl" % os.path.dirname(__file__)
            os.system("%s %s -e -hash eu -out %s" % (cmd, self.file_path, mtacfg_path))
            assert os.path.exists(mtacfg_path)

            return mtacfg_path

        def encode_cm():
            cmcfg_name=self.file.replace('.txt', '.cfg')
            cmcfg_path=os.path.join(self.dir_path, cmcfg_name)
            print("docsis -e %s /dev/null %s" % (self.file_path, cmcfg_path))
            os.system("docsis -e %s /dev/null %s" % (self.file_path, cmcfg_path))
            assert os.path.exists(cmcfg_path)

            return cmcfg_path

        if output_type == 'mta_cfg':
            return encode_mta()

        # default is CM cfg, if that fails we try to use special mta tool
        try:
            return encode_cm()
        except:
            return encode_mta()
