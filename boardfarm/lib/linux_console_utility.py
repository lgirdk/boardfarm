from boardfarm.devices.linux import LinuxDevice


class LinuxConsoleUtility:
    def __init__(self, parent_device: LinuxDevice):
        self.dev = parent_device

    def remove_resource(self, fname: str) -> None:
        """Removes the file from the arm console

        Args:
            fname (str): the filename or the complete path of the resource
        """
        cmd = f"rm {fname}"
        self.dev.sendline(cmd)
        self.dev.expect(self.dev.prompt)

    def get_date(self) -> str:
        """Get the dut date and time from arm console

        :return: dut date
        :rtype: str
        """
        return self.dev.get_date()
