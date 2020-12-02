import pexpect
import pytest

from boardfarm.devices.ser2net_connection import Ser2NetConnection
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper


class DummyDevice:
    def __init__(self):
        pass

    def expect(self, *args, **kwargs):
        pass


@pytest.mark.parametrize(
    "device, conn_cmd, expect_retval, msg, exp_raises",
    [
        (
            DummyDevice(),
            "connect somewhere",
            None,
            "Board is in use (connection refused).",
            pexpect.EOF("Intentional"),
        ),
        (
            DummyDevice(),
            "connect somewhere",
            0,
            "Password required and not supported",
            None,
        ),
        (
            DummyDevice(),
            "connect somewhere",
            1,
            "Board is in use (connection refused).",
            None,
        ),
        (DummyDevice(), "connect somewhere", 2, "", None),
        (DummyDevice(), "connect somewhere", 3, "", None),
        (DummyDevice(), "connect somewhere", 4, "", None),
    ],
)
def test_Ser2NetConnection(mocker, device, conn_cmd, expect_retval, msg, exp_raises):
    if exp_raises:
        mocker.patch.object(device, "expect", side_effect=exp_raises, autospec=True)
    else:
        mocker.patch.object(device, "expect", return_value=expect_retval)
    conn = Ser2NetConnection(device, conn_cmd)

    if msg:
        with pytest.raises(Exception) as e:
            conn.connect()
        assert str(e.value) == msg
    else:
        assert conn.connect(), "Test Ser2NetConnection Failed"
