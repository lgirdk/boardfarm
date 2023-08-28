import re

import pexpect

from boardfarm.exceptions import PexpectErrorTimeout, SNMPError
from boardfarm.lib.SnmpHelper import SnmpMibs

from .installers import install_snmp


class SNMPv2:
    """
    This class mainly executes snmp commands directly on the device machine to an ip address.
    Parameters:
        (bft_pexpect_helper.spawn) device : device used to perform snmp
        (str) ip : an ip address that defines the UdpTransportTarget used to perform snmp
    """

    def __init__(self, device, ip):
        self.device = device
        self.ip = ip
        self.snmpmibs_obj = SnmpMibs.default_mibs
        if not getattr(self.device, "snmp_installed", False):
            install_snmp(self.device)
            self.device.snmp_installed = True

    def _get_mib_oid(self, mib_name):
        oid_regex = r"^([1-9][0-9]{0,6}|0)(\.([1-9][0-9]{0,6}|0)){3,30}$"
        if re.match(oid_regex, mib_name):
            oid = mib_name
        else:
            try:
                oid = self.snmpmibs_obj.get_mib_oid(mib_name)
            except Exception as e:
                raise SNMPError(f"MIB not available, Error: {e}")
        return oid

    def snmpget(
        self,
        mib_name,
        index=0,
        community="private",
        extra_args="",
        timeout=10,
        retries=3,
    ):
        """
        Performs an snmp get on ip from device's console.
        Parameters:
            (str) mib_name : mib name used to perform snmp
            (int) index : index used along with mib_name
            (str) community: SNMP Community string that allows access to DUT, defaults to 'private'
            (str) extra_args: Any extra arguments to be passed in the command
            (int) timeout : timeout in seconds
            (int) retries : the no. of time the commands are executed on exception/timeout
        Returns:
            (list) result : value, value type and complete output
        """
        oid = self._get_mib_oid(mib_name) + f".{str(index)}"
        output = self.run_snmp(
            "snmpget", community, oid, timeout, retries, extra_args=extra_args
        )
        return self.parse_snmp_output(oid, output)

    def snmpset(
        self,
        mib_name,
        value,
        stype,
        index=0,
        community="private",
        extra_args="",
        timeout=10,
        retries=3,
    ):
        """
        Performs an snmp get on ip from device's console.
        Parameters:
            (str) mib_name : mib name used to perform snmp
            (str) value : value to be set for the mib name
            (str) stype : defines the datatype of value to be set for mib_name
                        stype: one of i, u, t, a, o, s, x, d, b
                        i: INTEGER, u: unsigned INTEGER, t: TIMETICKS, a: IPADDRESS
                        o: OBJID, s: STRING, x: HEX STRING, d: DECIMAL STRING, b: BITS
                        U: unsigned int64, I: signed int64, F: float, D: double
            (int) index : index used along with mib_name
            (str) community: SNMP Community string that allows access to DUT, defaults to 'private'
            (str) extra_args: Any extra arguments to be passed in the command
            (int) timeout : timeout in seconds
            (int) retries : the no. of time the commands are executed on exception/timeout
        Returns:
            (list) result : value, value type and complete output
        """
        oid = self._get_mib_oid(mib_name) + f".{str(index)}"

        if re.findall(r"\s", value.strip()) and stype == "s":
            value = f'"{value}"'
        if str(value).lower().startswith("0x"):
            value = value.upper()
            set_value = f"{stype} {value[2:]}"
        else:
            set_value = f"{stype} {value}"

        output = self.run_snmp(
            "snmpset",
            community,
            oid,
            timeout,
            retries,
            set_value=set_value,
            extra_args=extra_args,
        )
        return self.parse_snmp_output(oid, output, value)

    def run_snmp(
        self, action, community, oid, timeout, retries, set_value="", extra_args=""
    ):
        cmd = self.create_cmd(
            action, community, timeout, retries, oid, set_value, extra_args
        )
        return self.execute_snmp_cmd(cmd, timeout, retries)

    def create_cmd(
        self, action, community, timeout, retries, oid, set_value="", extra_args=""
    ):
        if extra_args:
            extra_args = " " + extra_args.strip()
        return "{} -v 2c -On{} -c {} -t {} -r {} {} {} {}".format(
            action,
            extra_args,
            community,
            str(timeout),
            str(retries),
            self.ip,
            oid,
            set_value,
        )

    def execute_snmp_cmd(self, cmd, timeout=10, retries=3):
        self.device.sendline(cmd)
        self.device.expect_exact(cmd)
        tout = timeout * retries * 2
        index = self.device.expect([pexpect.TIMEOUT, *self.device.prompt], timeout=tout)
        if index == 0:
            self.device.sendcontrol("c")
            self.device.expect_prompt()
            raise PexpectErrorTimeout("Timeout Occured while executing SNMP Command")

        return self.device.before

    def parse_snmp_output(self, oid, output, value=None):
        result_pattern = rf".{oid}\s+\=\s+((\S+)\:\s+(\"?.*\"?)|(\"?.*\"?))\r\n"
        match = re.search(result_pattern, output)
        if not match:
            raise SNMPError(output)
        if value:
            value = value.strip("'").strip("0x")
            assert (
                value in match[3]
            ), f"Set value did not match with output value: Expected: {value} Actual: {match[3]}"

        """Returns the list containing the get value, type of the value(if output is not empty string) and output recieved from snmp command"""
        if match[3]:
            return match[3].replace('"', ""), match[1], match.group()
        else:
            return match[1], match.group()

    def parse_snmpwalk_output(self, oid, output):
        result_pattern = rf".({oid}[\.\d+]*)\s+\=\s+(\S+)\:\s+(\"?.*\"?)\r\n"
        walk_key_value_dict = {}
        match = re.findall(result_pattern, output)
        if not match:
            raise SNMPError(output)
        else:
            for m in match:
                walk_key_value_dict[m[0]] = [m[2].replace('"', ""), m[1]]

        """returns list of dictionary of mib_oid as key and list(value, type) as value and complete output"""
        return walk_key_value_dict, output

    def snmpwalk(
        self,
        mib_name,
        index=None,
        community="private",
        retries=3,
        timeout=100,
        extra_args="",
    ):
        """
        Performs an snmp get on ip from device's console.
        Parameters:
            (str) mib_name : mib name used to perform snmp
            (int) index : index used along with mib_name
            (str) community: SNMP Community string that allows access to DUT, defaults to 'private'
            (int) retries : the no. of time the commands are executed on exception/timeout
            (int) timeout : timeout in seconds
        Returns:
            (list) result : dictionary of mib_oid as key and list(value, type) as value and complete output
        """
        if mib_name:
            try:
                oid = self._get_mib_oid(mib_name)
                if index:
                    oid = oid + f".{str(index)}"
            except Exception as e:
                raise SNMPError(f"MIB not available, Error: {e}")
        else:
            oid = ""

        output = self.run_snmp(
            "snmpwalk", community, oid, timeout, retries, extra_args=extra_args
        )
        return self.parse_snmpwalk_output(oid, output)

    def snmpbulkget(  # pylint: disable=too-many-arguments  # noqa: PLR0913
        self,
        mib_name: str,
        index: int = None,
        community: str = "private",
        non_repeaters: int = 0,
        max_repetitions: int = 10,
        retries: int = 3,
        timeout: int = 100,
        extra_args: str = "",
    ) -> list[tuple[str, str, str]]:
        """Perform SNMP bulkget on the device with given arguments.

        :param mib_name: mib name used to perform snmp
        :type mib_name: str
        :param index: index used along with mib_name, defaults to None
        :type index: int, optional
        :param community: SNMP Community string, defaults to "private"
        :type community: str, optional
        :param non_repeaters: value treated as get request, defaults to 0
        :type non_repeaters: int, optional
        :param max_repetitions: value treated as get next operation, defaults to 10
        :type max_repetitions: int, optional
        :param retries:  no.of time commands are executed on exception, defaults to 3
        :type retries: int, optional
        :param timeout: timeout in seconds, defaults to 100
        :type timeout: int, optional
        :param extra_args: extra arguments to be passed in the command, defaults to ""
        :type extra_args: str, optional
        :raises SNMPError: when MIB is not available
        :return: output of snmpbulkget command
        :rtype: list[tuple[str, str, str]]
        """
        if mib_name:
            try:
                oid = self._get_mib_oid(mib_name)
                if index:
                    oid = oid + f".{index!s}"
            except (ValueError, SNMPError) as exception:
                msg = f"MIB not available, Error: {exception}"
                raise SNMPError(msg) from exception
        else:
            oid = ""
        cmd = (
            f"snmpbulkget -v2c -On{extra_args} -Cn{non_repeaters} -Cr{max_repetitions}"
            f" -c {community} -t {timeout} -r {retries} {self.ip} {oid}"
            if extra_args
            else f"snmpbulkget -v2c -Cn{non_repeaters} -Cr{max_repetitions}"
            f" -c {community} -t {timeout} -r {retries} {self.ip} {oid}"
        )
        return self._parse_snmpbulk_output(self.execute_snmp_cmd(cmd, timeout, retries))

    def _parse_snmpbulk_output(self, output: str) -> list[tuple[str, str, str]]:
        """Return the tuple with snmp output, data type and the value.

        :param output: snmp bulk output
        :type output: str
        :raises SNMPError: when no matching output
        :return: parsed output
        :rtype: list[tuple[str, str, str]]
        """
        if not (match := re.findall(r"(iso[\.\d+]*\s\=\s(\S+)\:\s(\d+))", output)):
            err_msg = "Failed to parse the SNMP Bulk get output"
            raise SNMPError(err_msg)
        return match
