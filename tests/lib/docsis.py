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
        md5sum_check(encode_cfg_path_from_tmp_dir)
            return True if the content of cfg is same as original file.
    """
    def __init__(self, file_path):
        self.file_path=file_path
        self.dir_path=os.path.split(file_path)[0]
        self.file=os.path.split(file_path)[1]
        assert cmd_exists('docsis')

    def decode(self):
        if '.cfg' in self.file:
            os.system("docsis -d %s > %s" %(self.file_path, self.file_path.replace('.cfg', '.txt')))
            assert os.path.exists(self.file.replace('.cfg', '.txt'))

            return  self.file.replace('.cfg', '.txt')

    def encode(self, output_type='cm_cfg'):
        if '.txt' in self.file and output_type=='cm_cfg':
            cmcfg_name=self.file.replace('.txt', '.cfg')
            cmcfg_path=os.path.join(self.dir_path, cmcfg_name)
            os.system("docsis -e %s /dev/null %s" % (self.file_path, cmcfg_path))
            assert os.path.exists(cmcfg_path)
            assert self.md5sum_check(cmcfg_path), 'md5sum_check() fail'

            return  os.path.join(config.board['station'], cmcfg_name)
        elif '.txt' in self.file and output_type=='mta_cfg':
            mtacfg_name=self.file.replace('.txt', '.bin')
            mtacfg_path=os.path.join(self.dir_path, mtacfg_name)
            cmd = "tclsh %s/mta_conf.tcl" % os.path.dirname(__file__)
            os.system("%s %s -e -hash eu -out %s" % (cmd, self.file_path, mtacfg_path))
            assert os.path.exists(mtacfg_path)

            return  os.path.join(config.board['station'], mtacfg_name)

    def md5sum_check(self, encode_cfg_path):
        assert cmd_exists('md5sum')
        assert cmd_exists('sed')
        '''
        Command by manual
            ~$ docsis -na -d 9_EU_CBN_Dual-Stack_LG.cfg>txt
            ~$ sed -i ":a;N;s/\t\/\* Pad \*\/\n//g;$!ba" txt
            ~$ sed -e ":a;N;s/\t\/\* CmMic .* \*\/\n//g;$!ba" txt
            ~$ sed -e ":a;N;s/\t\/\* CmtsMic .* \*\/\n//g;$!ba" txt
            ~$ md5sum txt ../9_EU_CBN_Dual-Stack_LG.txt | awk '{print $1}'
        '''
        dir_path=os.path.split(encode_cfg_path)[0]

        os.system("docsis -na -d %s>%s/txt" % (encode_cfg_path, dir_path))
        os.system('sed -i \":a;N;s/\\t\/\* Pad \*\/\\n//g;$!ba" %s/txt' %dir_path)
        os.system('sed -i \":a;N;s/\\t\/\* CmMic .* \*\/\\n//g;$!ba" %s/txt' %dir_path)
        os.system('sed -i \":a;N;s/\\t\/\* CmtsMic .* \*\/\\n//g;$!ba" %s/txt' %dir_path)

        os.system('sed -i \":a;N;s/\\t\/\* Pad \*\/\\n//g;$!ba" %s' %encode_cfg_path.replace('.cfg', '.txt'))
        os.system('sed -i \":a;N;s/\\t\/\* CmMic .* \*\/\\n//g;$!ba" %s' %encode_cfg_path.replace('.cfg', '.txt'))
        os.system('sed -i \":a;N;s/\\t\/\* CmtsMic .* \*\/\\n//g;$!ba" %s' %encode_cfg_path.replace('.cfg', '.txt'))
        md5_req=os.popen("md5sum %s %s | awk \'{print $1}\'" %(encode_cfg_path.replace('.cfg', '.txt'), os.path.join(dir_path, 'txt'))).readlines()
        if md5_req[0]==md5_req[1]:
            return True
        else:
            return False
