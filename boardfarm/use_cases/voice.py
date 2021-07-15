"""Voice use cases library.

This module deals with only SIP end points.
All APIs are independent of board under test.
"""
from contextlib import contextmanager
from time import sleep

from boardfarm.devices.base_devices.sip_template import (
    SIPPhoneTemplate,
    SIPTemplate,
)
from boardfarm.exceptions import CodeError
from boardfarm.lib.network_testing import kill_process, tcpdump_capture


@contextmanager
def tcpdump(device: SIPTemplate, fname: str, filters: str = "") -> str:
    pid = None
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


def make_a_call(caller: SIPPhoneTemplate, callee: SIPPhoneTemplate) -> bool:
    """To make a call by caller to callee

    :param caller: SIP agent who intiates the call
    :type caller: SIPPhoneTemplate
    :param callee: SIP agent who receives the call
    :type callee: SIPPhoneTemplate
    :return: True if call succeeds
    :rtype: bool
    :raises CodeError: In case the call fails.
    """
    try:
        assert caller is not callee, "Caller and Caller cannot be same!"
        caller.call(callee)
        sleep(5)
    except Exception:
        raise CodeError(
            f"Failed to initiate a call between: {caller.name} --> {callee.name}"
        )
    return True


def answer_a_call(who_answers: SIPPhoneTemplate) -> bool:
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
    if not who_answers.is_ringing():
        raise CodeError(f"{who_answers.name} is not ringing!!")
    who_answers.answer()

    return who_answers.is_connected()


def disconnect_the_call(who_disconnects: SIPPhoneTemplate) -> bool:
    """Disconnecting a call on a SIP agent.

    The user will not verify if the call is ongoing.
    It will simply call the on_hook implementation.

    :param who_disconnects: SIP agent who is suppose to disconnect the call.
    :type who_disconnects: SIPPhoneTemplate
    :raises CodeError: In case disconnecting the call fails.
    :return: True if call is disconnected
    :rtype: bool
    """
    try:
        who_disconnects.on_hook()
        sleep(5)
    except Exception:
        raise CodeError(f"Failed to disconnect the call: {who_disconnects.name}")
    return True


def is_dialtone_detected(agent: SIPPhoneTemplate) -> bool:
    """Verify if a dialtone is detected off_hook.

    Device will be first placed on_hook.
    This is done to ensure disconnecting any previous sessions.

    After verifying dial tone device will again go back to on_hook state.

    :param agent: SIP agent used to verify dialtone.
    :type agent: SIPPhoneTemplate
    :return: True if dialtone is detected.
    :rtype: bool
    """
    agent.on_hook()
    return agent.detect_dialtone()


def is_line_busy(
    on_which_agent: SIPPhoneTemplate, who_is_busy: SIPPhoneTemplate
) -> bool:
    """To verify if the caller was notified that the callee is BUSY.

    Some phone will send this explicitly and will have RINGING 180
    as well inside their trace.

    :param on_which_agent: Caller who will receive BUSY
    :type on_which_agent: SIPPhoneTemplate
    :param who_is_busy: Callee who replies BUSY
    :type who_is_busy: SIPPhoneTemplate
    :return: True if caller received BUSY, else False
    :rtype: bool
    """
    assert on_which_agent is not who_is_busy, "Both args cannot be same"

    who_is_busy.reply_with_code(486)
    return on_which_agent.is_line_busy()


def is_call_not_answered(whose_call: SIPPhoneTemplate) -> bool:
    """Verify if callee did not pick up the call

    The Caller will receive a NO CARRIER or TIMEOUT reply.

    :param whose_call: Callee
    :type whose_call: SIPPhoneTemplate
    :return: True is not answered, else False
    :rtype: bool
    """
    return whose_call.is_call_not_answered()


def initialize_phone(target_phone: SIPPhoneTemplate, sip_proxy_ip: str) -> None:
    """Configure the phone, and start the application.

    :param target_phone: Target phone to be initialized.
    :type target_phone: SIPPhoneTemplate
    :param sip_proxy_ip: SIP proxy IP for capturing packets through it.
    :type sip_proxy_ip: str
    """
    target_phone.phone_config(sip_proxy_ip)
    target_phone.phone_start()
    target_phone.on_hook()


def shutdown_phone(target_phone: SIPPhoneTemplate) -> None:
    """Go on_hook and stop the phone application.

    :param target_phone: Target phone to be initialized.
    :type target_phone: SIPPhoneTemplate
    """
    target_phone.on_hook()
    target_phone.phone_kill()
