from boardfarm.lib.DeviceManager import get_device_by_name


def get_date_from_board() -> str:
    """Get the dut date and time from board console

    :return: dut date
    :rtype: str
    """
    board = get_device_by_name("board")
    return board.linux_console_utility.get_date()


def remove_resource_from_board(fname: str):
    """Removes the file from the board console

    Args:
        fname (str): the filename or the complete path of the resource
    """
    board = get_device_by_name("board")
    board.linux_console_utility.remove_resource(fname)
