# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time

def now_short():
    """
    Name:now_short
    Purpose: Get current date and time string
    Input:None
    Output:String in "YYYYMMDD-hhmmss" format
    """
    timeString = time.strftime("%Y%m%d-%H%M%S", time.localtime())+"\t"
    return timeString

def logfile_assert_message(s, condition, message):
	if not condition:
	   s.log_to_file += now_short()+message+": FAIL\r\n"
	   assert 0, message
	else:
	   s.log_to_file += now_short()+message+": PASS\r\n"
