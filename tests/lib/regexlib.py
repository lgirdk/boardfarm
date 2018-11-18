# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.


# Restrict all 4 numbers in the IP address to 0..255. It stores each of the 4
# numbers of the IP address into a capturing group. These groups can be used
# to further process the IP number.
ValidIpv4AddressRegex='(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)'
ValidIpv4AddressRegexWordBound='\b'+ValidIpv4AddressRegex+'\b'

# IPv6 text representation of addresses without compression from RFC 1884. This
# regular expression doesn't allow IPv6 compression (&quot;::&quot;) or mixed
# IPv4 addresses.
# Matches: FEDC:BA98:7654:3210:FEDC:BA98:7654:3210 | 1080:0:0:0:8:800:200C:417A | 0:0:0:0:0:0:0:1
ValidIpv6AddressRegex='([0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}'


# The CMTS mac-adderss format for e.g. 0025.2e34.4377
CmtsMacFormat='([0-9a-f]{4}\.[0-9a-fA-F]{4}\.[0-9a-f]{4})'


# traceroute returns no route to ip address (i.e. '<num> * * *' 30 times)
TracerouteNoRoute='((.[1-9]|[1-9][0-9])(\s\s\*\s\*\s\*)(\r\n|\r|\n)){30}'
