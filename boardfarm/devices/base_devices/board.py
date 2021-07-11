class BaseBoard:
    """Base class for the clean architecture model"""

    hw = None
    sw = None

    def __init__(self, *args, **kwargs):
        """Base implementation for board HW device."""
        raise NotImplementedError

    def wait_for_boot(self):
        """Enter boot loader menu, by interrupting boot-up of board's core.

        This method is called to flash new kernel images.
        """
        raise NotImplementedError

    def get_dns_server(self):
        """Get the DNS server configure on board by provisioner
        This detail is provided to LAN clients connected to board.

        :return: Ip of the nameserver
        :rtype: string
        """
        raise NotImplementedError

    def flash_linux(self, KERNEL):
        """This method flashes a new kernel image from the bootloader

        In order to flash a kernel we need to enter bootloader menu
        i.e. board.wait_for_boot()

        This method may inlcude the sourcing of the image file (usually via a
        local tftp server)

        :Param KERNEL: Pass the kernel image
        :type KERNEL: string
        """
        raise NotImplementedError

    def flash_rootfs(self, ROOTFS):
        """This method flashes a kernel image from the bootloader
        flash them on system core.

        In order to flash kernel with new image, we need to enter bootloader menu
        i.e. board.wait_for_boot()

        :Param ROOTFS: Pass the rootfs image which is passed via argument -r <image>
        :type ROOTFS: string
        """
        raise NotImplementedError

    def flash_all(self, COMBINED):
        """This method will download a COBINED image. using
        tftp and flash it for multiple core boards in a single call.

        In order to flash  with new image, we need to enter bootloader menu
        i.e. board.wait_for_boot()

        :Param ALL: Pass the combined SDK image
        :type ALL: string
        """
        raise NotImplementedError


class BaseBoardHw:
    """This class is a collection of APIs related to an embedded device HW
    configuration.
    It contains references to linux (i.e. SW) as currently all devices CPE devices are linux based.
    These APIs should be enough to flash the device from its Booloader.
    """

    mac_address = None
    power_port = None
    serial_no = None
    connecton_type = None
    consoles = {}

    def __init__(self, *args, **kwargs):
        raise NotImplementedError


class BaseBoardSw:
    """Placeholder for the SW side of the device, this could be removed in future and it is currently empty"""

    pass
