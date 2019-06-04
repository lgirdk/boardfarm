# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time
import re
from devices import prompt

#==============================================================================

DEFAULT_UNIT_TYPE = 'CH7465LG'
DEFAULT_UNIT_PROFILE = 'profileMV1'
DEFAULT_ACS_SHELL_USER = 'admin'

#==============================================================================

class FreeACS():

    model = "FreeACS"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.acs_user = kwargs['username']
        self.acs_pwd = kwargs['password']
        self.acs_ip = kwargs['ipaddr']
        self.acs_url = "http://" + self.acs_ip
        self.RemoteURL = self.acs_url + ":80/tr069"
        self.sleep_timing = 5

    name = "acs_server"

#==============================================================================

    def __str__(self):
        return "FreeACS"

#==============================================================================

    def close(self):
        pass
    
#==============================================================================

    def acs_login (self, dev):
        '''ACS server login'''
        # Telnet to ACS server
        ret = self.freeacs_telnet_login(dev, self.acs_ip, self.acs_user, self.acs_pwd)
        if ret != True:
            print ("\nERROR: Unable to login to ACS server...")
            return False

        # Open ACS server shell
        ret = self.freeacs_shell_open(dev)
        if ret != True:
            print ("\nERROR: Unable to start ACS shell...")
            self.freeacs_telnet_logout ()
            return False
        return True

#==============================================================================

    def acs_logout (self, dev):
        '''ACS server logout'''
        self.freeacs_shell_close (dev, self.acs_user)
        self.freeacs_telnet_logout (dev)
        return

#==============================================================================

    def acs_get_param (self, dev, unit_serial_no, param_name, param_flag="system"):

        return self.freeacs_get_param (dev, unit_serial_no, param_name, param_flag, DEFAULT_UNIT_PROFILE, DEFAULT_UNIT_TYPE)

#==============================================================================

    def acs_set_param (self, dev, unit_serial_no, param_name, param_value, param_flag="system"):
        return self.freeacs_set_param (dev, unit_serial_no, param_name, param_value, param_flag, DEFAULT_UNIT_PROFILE, DEFAULT_UNIT_TYPE)

#<<<<<<<<<<<<<<<<<<<<<<< FreeACS Specific functions <<<<<<<<<<<<<<<<<<<<<<<<<<<

    def freeacs_telnet_login (self, dev, acs_server_ip, acs_server_user, acs_server_pwd):
        '''Login to ACS server'''
        print ("freeacs_server_login: Current date & time " + time.strftime("%c"))
        try:
            dev.sendline('telnet %s' % acs_server_ip)
            dev.expect('login: ')
            dev.sendline('%s' % acs_server_user)
            dev.expect('Password:')
            dev.sendline('%s' % acs_server_pwd)
            dev.expect ('%s' % acs_server_user)
            #print ("\nSUCCESS: telnet login...")
            return True
        except:
            print ("\nERROR: telnet login Failed...")
            return False

#==============================================================================

    def freeacs_telnet_logout (self, dev):
        '''Logout ACS server'''
        print ("freeacs_server_logout: Current date & time " + time.strftime("%c"))
        try:
            dev.sendline('exit')
            dev.expect ('root')
            print ("\nSUCCESS: Terminating telnet with ACS Server...")
            return True
        except:
            print ("\nERROR: Terminating telnet with ACS Server...")
            return False

#==============================================================================

    def freeacs_shell_open (self, dev, username=DEFAULT_ACS_SHELL_USER):
        '''Opening ACS shell'''
        print ("freeacs_shell_open: Current date & time " + time.strftime("%c"))
        try:
            dev.sendline('fusionshell')
            dev.expect('/>')
            dev.sendline('1')
            dev.expect('Username: />')
            dev.sendline('%s' % username)
            dev.expect ('/>')
            #print ("\nSUCCESS: Opening ACS shell (fusionshell)...")
            return True
        except:
            print ("\nERROR: Launching ACS shell Failed...")
            return False

#==============================================================================

    def freeacs_shell_close (self, dev, acs_server_user):
        '''Closing ACS shell'''
        try:
            print ("freeacs_shell_close: Current date & time " + time.strftime("%c"))
            dev.sendline('exit')
            dev.expect ('%s' % acs_server_user)
            print ("\nSUCCESS: Closing ACS shell...")
            return True
        except:
            print ("\nERROR: Closing ACS shell...")
            return False

#==============================================================================

    def freeacs_select_unit_type (self, dev, unit_type=DEFAULT_UNIT_TYPE):
        '''Select Unit Type'''
        print ("freeacs_select_unit_type: unit type=%s" % unit_type)
        try:
            #cmd: cc /ut:CH7465LG
            dev.sendline('cc /ut:%s' % unit_type)
            dev.expect('%s/>' % unit_type)
            #print ("\nSUCCESS: Selecting unit type(acs_select_unit_type)...")
            return True
        except:
            print ("\nERROR: Selecting unit type(acs_select_unit_type)...")
            return False

#==============================================================================

    def freeacs_select_unit_profile (self, dev, unit_profile=DEFAULT_UNIT_PROFILE, unit_type=DEFAULT_UNIT_TYPE):
        '''Select profile'''
        print ("freeacs_select_unit_profile: unit type=%s, profile=%s" % (unit_type, unit_profile))
        try:
            #cmd: cc /ut:CH7465LG/pr:profileMV1
            dev.sendline('cc /ut:%s/pr:%s' % (unit_type, unit_profile))
            dev.expect('%s/>' % unit_profile)
            #print ("\nSUCCESS: Selecting unit type/profile(acs_select_unit_profile)...")
            return True
        except:
            print ("\nERROR: Selecting unit type/profile(acs_select_unit_profile)...")
            return False

#==============================================================================

    def freeacs_select_unit(self, dev, unit_serial_no, unit_profile=DEFAULT_UNIT_PROFILE, unit_type=DEFAULT_UNIT_TYPE):
        '''Select Unit'''
        print ("freeacs_select_unit: unit type=%s, profile=%s, unit serial no=%s" % (unit_type, unit_profile, unit_serial_no))
        try:
            #unit ID is MV1-<unit_serial_no>
            #cmd: cc /ut:CH7465LG/pr:profileMV1/un:MV1-DDAP6287091A
            tmpStr = "cc /ut:%s/pr:%s/un:MV1-%s\r\n" % (unit_type, unit_profile, unit_serial_no)
            dev.sendline('%s' % tmpStr)
            dev.expect('%s/>' % unit_serial_no)
            #print ("\nSUCCESS: Selecting unit(acs_select_unit)...")
            return True
        except:
            print ("\nERROR: Selecting unit(acs_select_unit)...")
            return False

#==============================================================================

    def freeacs_get_param (self, dev, unit_serial_no, param_name, param_flag="system", unit_profile=DEFAULT_UNIT_PROFILE, unit_type=DEFAULT_UNIT_TYPE):
        '''Read parameter from ACS'''
        print ("freeacs_get_param: unit type=%s, profile=%s, unit serial no=%s, param name=%s" % (unit_type, unit_profile, unit_serial_no, param_name))
        read_value = ""
        try:
            if param_flag != "system":
                # Set unit type
                if True != self.freeacs_select_unit_type (dev, unit_type):
                    raise Exception
                # Set parameter flag Always-Read (RA)
                # e.g. cmd: setparam Device.WiFi.SSID.1.SSID RA
                tmpStr = "setparam %s RA" % param_name
                dev.sendline('%s' % tmpStr)
                tmpStr = "The unit type parameter %s is changed" % param_name
                dev.expect(tmpStr)
                # Select unit
                if True != self.freeacs_select_unit(dev, unit_serial_no, unit_profile, unit_type):
                    raise Exception
                # Send provision command
                dev.sendline('provision')
                dev.expect("SUCCESS: Device has connected to Fusion")
            # Read parameter
            tmpStr = "listunitparams  %s" % param_name
            dev.sendline('%s' % tmpStr)
            dev.expect('\n%s\s+([^\r\n]*)\r\n' % param_name)
            read_value = dev.match.group(1)
            read_value = read_value.strip()
            dev.expect('%s/>' % unit_serial_no)
            #print ("\nSUCCESS: Reading a parameter,acs_get_param (%s=%s)" % (param_name, read_value))
            return True, read_value
        except:
            print ("\nERROR: Reading a parameter(acs_get_param)...")
            return False, read_value

#==============================================================================

    def freeacs_set_param (self, dev, unit_serial_no, param_name, param_value, param_flag="system", unit_profile=DEFAULT_UNIT_PROFILE, unit_type=DEFAULT_UNIT_TYPE):
        '''Write parameter from ACS'''
        print ("freeacs_set_param: Unit type=%s, profile=%s, unit serial no=%s, param name=%s, param value=%s" % (unit_type, unit_profile, unit_serial_no, param_name, param_value))
        try:
            if param_flag == "system":
                print "\nERROR: Skip writting system parameters..."
                return False
            # Set unit type
            if True != self.freeacs_select_unit_type (dev, unit_type):
                raise Exception
            # Set parameter flag Read/Write (RW)
            # e.g. cmd: setparam Device.WiFi.SSID.1.SSID RW
            tmpStr = "setparam %s RW" % param_name
            dev.sendline('%s' % tmpStr)
            tmpStr = "The unit type parameter %s is changed" % param_name
            dev.expect(tmpStr)
            # Select unit
            if True != self.freeacs_select_unit(dev, unit_serial_no, unit_profile, unit_type):
                raise Exception
            # Write parameter
            tmpStr = "setparam  %s %s" % (param_name, param_value)
            dev.sendline('%s' % tmpStr)
            tmpStr = "The unit parameter %s is changed" % param_name
            dev.expect(tmpStr)
            # Send provision command
            dev.sendline('provision')
            dev.expect("SUCCESS: Device has connected to Fusion")
            dev.expect('%s/>' % unit_serial_no)
            #print ("\nSUCCESS: Writting a parameter(acs_set_param)...")
            return True
        except:
            print ("\nERROR: Writting a parameter(acs_set_param)...")
            return False

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
