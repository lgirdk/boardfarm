import pytest

from boardfarm.devices.base_devices.sip_template import SIPPhoneTemplate
from boardfarm.exceptions import CodeError
from boardfarm.use_cases import voice


# since SIPPhoneTemplate has abstract methods
class DummySIPEndpoint(SIPPhoneTemplate):
    model = "dummy_phone"

    def __init__(self, name, number):
        self.own_number = number
        self.name = name

    @property
    def number(self):
        return self.own_number

    def phone_start(self) -> None:
        print("Phone started")

    def phone_config(self, sip_server: str = "") -> None:
        print(f"Phone configured with number {self.number}")

    def phone_kill(self) -> None:
        print("Phone killed")

    def on_hook(self) -> None:
        pass

    def off_hook(self) -> None:
        pass

    def answer(self) -> bool:
        return True

    def call(self, callee: "SIPPhoneTemplate") -> None:
        print(f"calling {callee.name}:{callee.number} ...")

    def is_ringing(self) -> bool:
        return True

    def is_connected(self) -> bool:
        print(f"Call connected to {self.name}")
        return True

    def is_onhold(self) -> bool:
        return False

    def is_playing_dialtone(self) -> bool:
        return False

    def is_call_ended(self) -> bool:
        return False

    def is_code_ended(self) -> bool:
        return False

    def is_call_waiting(self) -> bool:
        return False

    def is_in_conference(self) -> bool:
        return False

    def has_off_hook_warning(self) -> bool:
        return False

    def disable_call_waiting_overall(self):
        pass

    def disable_call_waiting_per_call(self):
        pass

    def enable_call_forwarding_busy(self):
        pass

    def enable_call_waiting(self):
        pass

    def is_dialing(self) -> bool:
        return True

    def is_idle(self) -> bool:
        return True

    def is_incall_connected(self) -> bool:
        return True

    def is_incall_dialing(self) -> bool:
        return True

    def is_incall_playing_dialtone(self) -> bool:
        return True

    def detect_dialtone(self) -> bool:
        return True

    def is_line_busy(self) -> bool:
        return False

    def reply_with_code(self, code: int) -> None:
        print(f"Returning code {code} as reply ...")

    def is_call_not_answered(self) -> bool:
        return False

    def answer_waiting_call(self) -> None:
        pass

    def toggle_call(self) -> None:
        pass

    def merge_two_calls(self) -> None:
        pass

    def reject_waiting_call(self) -> None:
        pass

    def place_call_onhold(self) -> None:
        pass

    def press_R_button(self) -> None:
        pass

    def hook_flash(self) -> None:
        pass


class DummySIPEndpoint2(SIPPhoneTemplate):
    pass


@pytest.fixture
def voice_resources():
    A, B = DummySIPEndpoint("A", 1000), DummySIPEndpoint("B", 2000)

    A = voice.VoiceClient("A", "", 1000, A)
    B = voice.VoiceClient("B", "", 1000, B)

    yield A, B


def test_answer_call_negative(mocker, voice_resources):
    """A dials B, B not ringing, B answers call fails"""
    _, B = voice_resources
    mocker.patch.object(B._obj(), "is_ringing", return_value=False, autospec=True)
    with pytest.raises(CodeError) as e:
        voice.answer_a_call(who_answers=B)

    assert str(e.value) == "B is not ringing!!"
    voice.disconnect_the_call(who_disconnects=B)


def test_make_call_negative(voice_resources):
    """A calls A must fail"""
    A, _ = voice_resources
    with pytest.raises(CodeError) as e:
        voice.make_a_call(caller=A, callee=A)
    assert str(e.value) == "Failed to initiate a call between: A --> A"


def test_is_busy_negative(voice_resources):
    """A calls B, A cannot check A is busy"""
    A, _ = voice_resources
    with pytest.raises(AssertionError) as e:
        voice.is_line_busy(on_which_agent=A, who_is_busy=A)
    assert str(e.value) == "Both args cannot be same"


def test_sip_template_negative(voice_resources):
    """A calls B, A cannot check A is busy"""
    with pytest.raises(TypeError) as e:
        print(DummySIPEndpoint2())  # pylint: disable=abstract-class-instantiated
    assert "Can't instantiate abstract class DummySIPEndpoint2" in str(e.value)
