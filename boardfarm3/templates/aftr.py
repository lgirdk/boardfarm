"""Boardfarm AFTR template."""

from abc import ABC, abstractmethod

from boardfarm3.templates.cpe.cpe import CPE
from boardfarm3.templates.wan import WAN


class AFTR(ABC):  # pylint: disable=R0903
    """Boardfarm AFTR template."""

    @abstractmethod
    def configure_aftr(self, wan: WAN, board: CPE) -> None:
        """Configure aftr.

        :param wan: WAN Device
        :type wan: WAN
        :param board: CPE Device
        :type board: CPE
        """
        raise NotImplementedError

    @abstractmethod
    def restart_aftr_process(self, wan: WAN) -> None:
        """Restart aftr proess.

        This is to ensure the ipv4 connectivity.

        :param wan: WAN Device
        :type wan: WAN
        """
        raise NotImplementedError
