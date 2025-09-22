"""PrplOS GUI LCM Page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from selenium.common.exceptions import NoSuchElementException

from boardfarm3.lib.gui.prplos.pages.page_helper import get_element_by_css
from boardfarm3.lib.gui.prplos.pages.prplos_base_pom import PrplOSBasePOM

if TYPE_CHECKING:
    from ipaddress import IPv4Address

    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support.events import EventFiringWebDriver


_SUBMENU_CSS = "#ember9"
_HEADER_CSS = ".content > h2:nth-child(1)"


class LCMPage(PrplOSBasePOM):
    """Page Object for LCM page."""

    def __init__(
        self,
        driver: WebDriver | EventFiringWebDriver,
        gw_ip: str | IPv4Address,
        fluent_wait: int = 20,
    ) -> None:
        """Initialize LCMPage POM.

        :param driver: webdriver instance
        :type driver: WebDriver | EventFiringWebDriver
        :param gw_ip: gateway ip address
        :type gw_ip: str | IPv4Address
        :param fluent_wait: timeout in seconds to load the page, defaults to 20
        :type fluent_wait: int
        """
        super().__init__(driver, gw_ip, fluent_wait)
        try:
            if self.networking_lcm_header.is_displayed():
                return  # Do not click open sub-menu if it is already open
        except NoSuchElementException:
            pass
        self.click_networking_submenu(get_element_by_css(self, _SUBMENU_CSS))
        self.wait.until(self.is_page_loaded)

    def is_page_loaded(self, driver: WebDriver | EventFiringWebDriver) -> bool:
        """Verify the home page is completely loaded.

        :param driver: webdriver instance
        :type driver: WebDriver | EventFiringWebDriver
        :return: True if home page is loaded
        :rtype: bool
        """
        return self.networking_lcm_header.is_displayed() and driver.execute_script(
            "return document.readyState == 'complete'"
        )

    @property
    def networking_lcm_header(self) -> WebElement:
        """The LCM header element.

        :return: the web element
        :rtype: WebElement
        :raises NoSuchElementException: if not found
        """
        element = get_element_by_css(self, _HEADER_CSS)
        if element.text == "LCM":
            return element
        msg = f"networking_lcm_header: {_HEADER_CSS}"
        raise NoSuchElementException(msg)
