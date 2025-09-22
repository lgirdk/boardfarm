"""CPE template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardfarm3.templates.cpe.cpe_hw import CPEHW
    from boardfarm3.templates.cpe.cpe_sw import CPESW


class CPE(ABC):
    """CPE Template."""

    @property
    @abstractmethod
    def config(self) -> dict:
        """Device configuration."""
        raise NotImplementedError

    @property
    @abstractmethod
    def hw(self) -> CPEHW:  # pylint: disable=invalid-name
        """CPE Hardware."""
        raise NotImplementedError

    @property
    @abstractmethod
    def sw(self) -> CPESW:  # pylint: disable=invalid-name
        """CPE Software."""
        raise NotImplementedError
