# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import os

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
    def __init__(self, file_path):
        self.file_path=file_path
        self.dir_path=os.path.split(file_path)[0]
        self.file=os.path.split(file_path)[1]

    def decode(self):
        if '.cfg' in self.file:
            os.system("docsis -d %s > %s" %(self.file_path, self.file_path.replace('.cfg', '.txt')))
            return  self.file.replace('.cfg', '.txt')
    def encode(self, output_type='cm_cfg'):
        """docsis need a not emtpy of key file for encode"""
        if not os.path.exists("%s/key" %self.dir_path):
            os.system("echo key > %s/key" %self.dir_path)
        if '.txt' in self.file and output_type=='cm_cfg':
            os.system("docsis -e %s %s %s" % (self.file_path, self.dir_path+'/key', self.file_path.replace('.txt', '.cfg')))
            return  self.file.replace('.txt', '.cfg')
        elif '.txt' in self.file and output_type=='mta_cfg':
            os.system("docsis -p %s %s" % (self.file_path, self.file_path.replace('.txt', '.bin')))
            return  self.file.replace('.txt', '.bin')
