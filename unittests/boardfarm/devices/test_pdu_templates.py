import sys

import pytest

from boardfarm.devices.base_devices.pdu_templates import PDUTemplate


@pytest.fixture
def inst_fail_msg():
    """Pre-Python 3.9 error message is in plural form"""
    if sys.version_info < (3, 9):
        msg = "Can't instantiate abstract class MyPDU with abstract methods"
    else:
        msg = "Can't instantiate abstract class MyPDU with abstract method"
    yield msg


def test_cannot_instantiate_abc_pdu():
    # The argument for PDUTemplate() has not been passed as part of unitttest check, hence diabling pylint error
    with pytest.raises(TypeError) as err:
        pdu = PDUTemplate()  # pylint: disable=E1120
    assert "PDUTemplate with abstract methods _connect, reset, turn_off" in str(
        err.value
    )


def test_cannot_instantiate_derived_pdu_missing_connect(inst_fail_msg):
    exp_err_msg = f"{inst_fail_msg} _connect"
    with pytest.raises(TypeError) as err:
        # missing "_connect" property definition
        class MyPDU(PDUTemplate):
            def __init__(self, ip_address: str, **kwargs):
                super().__init__(ip_address)

            def reset(self):
                pass

            def turn_off(self):
                pass

        pdu = MyPDU("127.0.0.1")
    assert exp_err_msg in str(err.value)


def test_cannot_instantiate_derived_pdu_wrong_signature_reset():
    with pytest.raises(TypeError) as err:
        # wrong signature on reset(), "dummy" parameter added
        class MyPDU(PDUTemplate):
            def __init__(self, ip_address: str, **kwargs):
                super().__init__(ip_address)
                self._connect()

            def _connect(self):
                pass

            def reset(self, dummy):
                pass

            def turn_off(self):
                pass

        pdu = MyPDU(
            "127.0.0.1",
        )
    assert (
        "Abstract method 'reset'  not implemented with correct signature in 'MyPDU'."
        in str(err.value)
    )


def test_cannot_instantiate_derived_pdu_without_init_no_args():
    with pytest.raises(TypeError) as err:
        # No Arguments on instance and absence of __init__ in derived class
        class MyPDU(PDUTemplate):
            def _connect(self):
                pass

            def reset(self):
                pass

            def turn_off(self):
                pass

        # The argument for MyPDU() has not been passed as part of unitttest check, hence diabling pylint error
        pdu = MyPDU()  # pylint: disable=E1120
    assert "__init__() missing 1 required positional argument: 'ip_address'" in str(
        err.value
    )


def test_cannot_instantiate_derived_pdu_without_init_correct_args():
    # Correct signature without __init__ in derived class
    class MyPDU(PDUTemplate):
        def _connect(self):
            pass

        def reset(self):
            pass

        def turn_off(self):
            pass

    pdu = MyPDU("127.0.0.1", "username", "password", 23, "sample_outlet")


def test_instantiate_derived_pdu():
    class MyPDU(PDUTemplate):
        def __init__(self, ip_address, outlet, username, password):
            super().__init__(ip_address, username, password, outlet=outlet)
            self._connect()

        def _connect(self):
            assert not self.pcon

        def reset(self):
            pass

        def turn_off(self):
            pass

    pdu = MyPDU("127.0.0.1", "sample_outlet", "username", "password")


def test_instantiate_derived_pdu_extra_method():
    class MyPDU(PDUTemplate):
        def __init__(self, ip_address=None):
            super().__init__("127.0.0.1", "username", "password", 23, "sample_outlet")
            self._connect()

        def _connect(self):
            self.pcon = "Not None"

        def __on(self):
            pass

        def __off(self):
            pass

        def reset(self):
            assert self.pcon
            self.__on()
            self.__off()

        def turn_off(self):
            assert self.pcon
            self.__off()

    pdu = MyPDU()
