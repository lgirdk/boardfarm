from abc import ABC, abstractmethod
from typing import Dict, List

from aenum import Enum


def generate_call_states(**kwargs) -> Enum:
    """Factory method to return call states for a FXO component.

    :return: CallStates derived from Enum
    :rtype: Enum
    """

    class CallStates(Enum):
        idle = kwargs.pop("idle")
        dialing = kwargs.pop("dialing")
        incall_dialing = kwargs.pop("incall_dialing")
        ringing = kwargs.pop("ringing")
        connected = kwargs.pop("connected")
        incall_connected = kwargs.pop("incall_connected")
        on_hold = kwargs.pop("on_hold")
        playing_dialtone = kwargs.pop("playing_dialtone")
        incall_playing_dialtone = kwargs.pop("incall_playing_dialtone")
        call_ended = kwargs.pop("call_ended")
        code_ended = kwargs.pop("code_ended")
        call_waiting = kwargs.pop("call_waiting")
        conference = kwargs.pop("conference")
        off_hook_warning = kwargs.pop("off_hook_warning")
        faxcall_pending = kwargs.pop("faxcall_pending")

    return CallStates


class FXOTemplate(ABC):
    TOTAL_LINES: int

    @property
    @abstractmethod
    def call_states(self) -> Dict[str, str]:
        """Return a dicitionary of all call states supported by the FXO component.

        States to be covered:
            - Idle
            - Dialing
            - Ringing
            - Connected
            - OnHold
            - Playing Dialtone
            - Incall Playing Dialtone
            - Call Ended
            - Code Ended
            - Call Waiting
            - Conferencing
            - Faxcall Pending
            - Offhook Warning
            - Incall Connected
            - Incall In Progress

        Please refer to generate_call_states method.

        :return: Call state dictionary
        :rtype: dict
        """
        return {}

    @abstractmethod
    def get_fxs_call_state(self, fxs_port: str) -> List[Enum]:
        """[summary]

        :param fxs_port: [description]
        :type fxs_port: [type]
        :raises NotImplementedError: [description]
        :return: [description]
        :rtype: List[Enum]
        """
        raise NotImplementedError

    @abstractmethod
    def check_call_state(self, fxs_port: str, state: Enum, operator: str = "^") -> bool:
        """Contains the logic to check the state of the lines based on the no. of lines
        :param fxs_port: fxs port number
        :type fxs_port: String
        :param state: call state
        :type state: Enum
        :param operator: Logical operator that states the decision to check for the states on different lines (^ stands for XOR)
        :type operator: string
        :return: Returns True if only either of the lines has the desired state but not more than one
        :rtype: bool"""

    @abstractmethod
    def __init__(self) -> None:
        self.states = generate_call_states(**self.call_states)
