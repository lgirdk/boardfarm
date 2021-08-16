import sys

import pytest

from boardfarm.devices.base_devices.board_templates import BoardTemplate


@pytest.fixture
def inst_fail_msg():
    """Pre-Python 3.9 error message is in plural form"""
    if sys.version_info < (3, 9):
        msg = "Can't instantiate abstract class MyBoard with abstract methods"
    else:
        msg = "Can't instantiate abstract class MyBoard with abstract method"
    yield msg


def test_cannot_instantiate_abc_board():
    with pytest.raises(TypeError) as err:
        board = BoardTemplate()  # noqa: F841
    assert (
        "BoardTemplate with abstract methods close, cm_mac, factory_reset, flash, hw, model, reset, sw"
        in str(err.value)
    )


def test_cannot_instantiate_derived_board_missing_model(inst_fail_msg):
    exp_err_msg = f"{inst_fail_msg} model"
    with pytest.raises(TypeError) as err:
        # missing "model" property definition
        class MyBoard(BoardTemplate):
            hw = "some_hw_object"
            sw = "some_sw_object"
            cm_mac = None

            def __init__(self, *args, **kwargs):
                pass

            def flash(self, image: str, method: str = None):
                pass

            def reset(self, method: str = None):
                pass

            def factory_reset(self, method: str = None) -> bool:
                pass

            def close(self):
                return super().close()

        board = MyBoard()  # noqa: F841
    assert exp_err_msg in str(err.value)


def test_cannot_instantiate_derived_board_missing_hw(inst_fail_msg):
    exp_err_msg = f"{inst_fail_msg} hw"
    with pytest.raises(TypeError) as err:
        # missing "hw" property definition
        class MyBoard(BoardTemplate):
            model = "MyBoard"
            sw = "some_sw_object"
            cm_mac = None

            def __init__(self, *args, **kwargs):
                pass

            def flash(self, image: str, method: str = None):
                pass

            def reset(self, method: str = None):
                pass

            def factory_reset(self, method: str = None) -> bool:
                pass

            def close(self):
                return super().close()

        board = MyBoard()  # noqa: F841
    assert exp_err_msg in str(err.value)


def test_cannot_instantiate_derived_board_missing_close(inst_fail_msg):
    exp_err_msg = f"{inst_fail_msg} close"
    with pytest.raises(TypeError) as err:
        # missing "close" method definition
        class MyBoard(BoardTemplate):
            model = "MyBoard"
            hw = "some_hw_obj"
            sw = "some_sw_object"
            cm_mac = None

            def __init__(self, *args, **kwargs):
                pass

            def flash(self, image: str, method: str = None):
                pass

            def reset(self, method: str = None):
                pass

            def factory_reset(self, method: str = None) -> bool:
                pass

        board = MyBoard()  # noqa: F841
    assert exp_err_msg in str(err.value)


def test_cannot_instantiate_derived_board_wrong_signature():
    with pytest.raises(TypeError) as err:
        # wrong signature on flash(), "whatever" parameter added
        class MyBoard(BoardTemplate):
            model = "MyBoard"
            hw = "some_hw_object"
            sw = "some_sw_object"
            cm_mac = None

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            def flash(self, image: str, method: str = None, whatever: object = None):
                pass

            def reset(self, method: str = None):
                pass

            def factory_reset(self, method: str = None):
                pass

            def close(self):
                return super().close()

        board = MyBoard()  # noqa: F841
    assert (
        "Abstract method 'flash'  not implemented with correct signature in 'MyBoard'"
        in str(err.value)
    )


def test_instantiate_derived_board():
    class MyBoard(BoardTemplate):
        model = "MyBoard"
        hw = "some_hw_object"
        sw = "some_sw_object"
        cm_mac = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def flash(self, image: str, method: str = None):
            pass

        def reset(self, method: str = None):
            pass

        def factory_reset(self, method: str = None) -> bool:
            pass

        def close(self):
            return super().close()

    board = MyBoard()  # noqa: F841
