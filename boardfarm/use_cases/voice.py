"""Voice use cases library.

This module deals with only SIP end points.
All APIs are independent of board under test.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from time import sleep
from typing import Generator

from boardfarm.devices.base_devices.sip_template import (
    SIPPhoneTemplate,
    SIPTemplate,
)
from boardfarm.exceptions import CodeError
from boardfarm.lib.DeviceManager import get_device_by_name
from boardfarm.lib.network_testing import kill_process, tcpdump_capture


@dataclass
class VoiceClient:
    name: str
    ip: str
    number: str
    __obj: SIPPhoneTemplate

    def _obj(self):
        return self.__obj


@dataclass
class VoiceServer:
    name: str
    ip: str
    __obj: SIPTemplate

    def _obj(self):
        return self.__obj


def get_sip_proxy() -> VoiceServer:
    """Initialize and return SIP proxy details.

    :return: name and IP details of SIP proxy.
    :rtype: VoiceServer
    """
    sip_proxy: SIPTemplate = get_device_by_name("sipcenter")
    return VoiceServer(sip_proxy.name, str(sip_proxy.gw), sip_proxy)


@contextmanager
def tcpdump(
    dev: VoiceServer, fname: str, filters: str = ""
) -> Generator[str, None, None]:
    pid: str = ""
    device = dev._obj()
    try:
        pid = tcpdump_capture(
            device,
            device.iface_dut,
            capture_file=fname,
            return_pid=True,
            additional_filters=f"-s0 {filters}",
        )
        yield pid
    finally:
        kill_process(device, process="tcpdump", pid=pid)


def make_a_call(caller: VoiceClient, callee: VoiceClient) -> bool:
    """To make a call by caller to callee

    :param caller: SIP agent who intiates the call
    :type caller: VoiceClient
    :param callee: SIP agent who receives the call
    :type callee: VoiceClient
    :return: True if call succeeds
    :rtype: bool
    :raises CodeError: In case the call fails.
    """
    try:
        assert caller is not callee, "Caller and Caller cannot be same!"
        caller._obj().call(callee._obj())
        sleep(5)
    except Exception:
        raise CodeError(
            f"Failed to initiate a call between: {caller.name} --> {callee.name}"
        )
    return True


def answer_a_call(who_answers: VoiceClient) -> bool:
    """Answer a ringing call by target SIP agent.

    Execution order:
    - Ensure there is a ring on the target agent.
    - Pick up the call
    - Ensure the line is connected

    :param who_answers: SIP agent who is suppose to answer the call.
    :type who_answers: SIPPhoneTemplate
    :return: True if call is connected, else False
    :rtype: bool
    :raises CodeError: In case answering the call fails.
    """
    if not who_answers._obj().is_ringing():
        raise CodeError(f"{who_answers._obj().name} is not ringing!!")
    who_answers._obj().answer()

    return who_answers._obj().is_connected()


def disconnect_the_call(who_disconnects: VoiceClient) -> bool:
    """Disconnecting a call on a SIP agent.

    The user will not verify if the call is ongoing.
    It will simply call the on_hook implementation.

    :param who_disconnects: SIP agent who is suppose to disconnect the call.
    :type who_disconnects: VoiceClient
    :raises CodeError: In case disconnecting the call fails.
    :return: True if call is disconnected
    :rtype: bool
    """
    try:
        who_disconnects._obj().on_hook()
        sleep(5)
    except Exception:
        raise CodeError(f"Failed to disconnect the call: {who_disconnects.name}")
    return True


def is_dialtone_detected(agent: VoiceClient) -> bool:
    """Verify if a dialtone is detected off_hook.

    Device will be first placed on_hook.
    This is done to ensure disconnecting any previous sessions.

    After verifying dial tone device will again go back to on_hook state.

    :param agent: SIP agent used to verify dialtone.
    :type agent: VoiceClient
    :return: True if dialtone is detected.
    :rtype: bool
    """
    agent._obj().on_hook()
    return agent._obj().detect_dialtone()


def is_line_busy(on_which_agent: VoiceClient, who_is_busy: VoiceClient) -> bool:
    """To verify if the caller was notified that the callee is BUSY.

    Some phone will send this explicitly and will have RINGING 180
    as well inside their trace.

    :param on_which_agent: Caller who will receive BUSY
    :type on_which_agent: VoiceClient
    :param who_is_busy: Callee who replies BUSY
    :type who_is_busy: VoiceClient
    :return: True if caller received BUSY, else False
    :rtype: bool
    """
    assert on_which_agent is not who_is_busy, "Both args cannot be same"

    who_is_busy._obj().reply_with_code(486)
    return on_which_agent._obj().is_line_busy()


def is_call_not_answered(whose_call: VoiceClient) -> bool:
    """Verify if callee did not pick up the call

    The Caller will receive a NO CARRIER or TIMEOUT reply.

    :param whose_call: Callee
    :type whose_call: VoiceClient
    :return: True is not answered, else False
    :rtype: bool
    """
    return whose_call._obj().is_call_not_answered()


def initialize_phone(target_phone: str) -> VoiceClient:
    """Configure the phone, and start the application.

    :param target_phone: Target phone to be initialized.
    :type target_phone: str
    """
    dev: SIPPhoneTemplate = get_device_by_name(target_phone)
    sip_proxy: SIPTemplate = get_device_by_name("sipcenter")

    dev.phone_config(str(sip_proxy.gw))
    dev.phone_start()
    dev.on_hook()

    return VoiceClient(dev.name, str(dev.gw), dev.number, dev)


def shutdown_phone(target_phone: VoiceClient) -> None:
    """Go on_hook and stop the phone application.

    :param target_phone: Target phone to be initialized.
    :type target_phone: SIPPhoneTemplate
    """
    dev = target_phone._obj()
    dev.on_hook()
    dev.phone_kill()
