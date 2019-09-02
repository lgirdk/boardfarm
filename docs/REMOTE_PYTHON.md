ASYNCHRONOUS SNMP:

With asyncio built-in facilities, you could run many SNMP queries in parallel and/or sequentially, interleave SNMP queries with I/O operations with other systems. See asyncio resources repository for other asyncio-compatible modules.

FUNCTION PATH: boardfarm/tests/lib/common.py
ASYNCRONOUS SCRIPT PATH: boardfarm/tests/lib/scripts/asyncore_snmp.py

USAGE:
snmp_asyncore_walk(device, ip_address, mib_oid, community='public', time_out=100)

EXAMPLE:
output = snmp_asyncore_walk(wan, cm_ipv6, “1.3”, private, 150)

OUTPUT:
Return value is True or False

TESTCASE USAGE:
from lib.common import snmp_asyncore_walk
snmp_asyncore_walk(device, ip_address, mib_oid, community='public', time_out=100)

SCRIPT WORKING DESCRIPTION:
As the snmpwalk is executed, the output is redirected to a file. Once the snmpwalk has completed the output file size is checked (i.e. it is not 0KB).
The function returns True if the walk was successful, False otherwise.
