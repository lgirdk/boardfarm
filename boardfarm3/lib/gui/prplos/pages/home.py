"""PrplOS GUI Home Page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from boardfarm3.lib.gui.prplos.pages.page_helper import get_element_by_css
from boardfarm3.lib.gui.prplos.pages.prplos_base_pom import PrplOSBasePOM

if TYPE_CHECKING:
    from ipaddress import IPv4Address

    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support.events import EventFiringWebDriver


class HomePage(PrplOSBasePOM):
    """Page Object for Home page."""

    def __init__(
        self,
        driver: WebDriver | EventFiringWebDriver,
        gw_ip: str | IPv4Address,
        fluent_wait: int = 20,
    ) -> None:
        """Initialize HomePage POM.

        :param driver: webdriver instance
        :type driver: WebDriver | EventFiringWebDriver
        :param gw_ip: gateway ip address
        :type gw_ip: str | IPv4Address
        :param fluent_wait: timeout in seconds to load the page, defaults to 20
        :type fluent_wait: int
        """
        super().__init__(driver, gw_ip, fluent_wait)
        self.wait.until(self.is_page_loaded)

    def is_page_loaded(self, driver: WebDriver | EventFiringWebDriver) -> bool:
        """Verify the home page is completely loaded.

        :param driver: webdriver instance
        :type driver: WebDriver | EventFiringWebDriver
        :return: True if home page is loaded, Otherwise False
        :rtype: bool
        """
        return self.system_info_element.is_displayed() and driver.execute_script(
            "return document.readyState == 'complete'"
        )

    @property
    def system_info_element(self) -> WebElement:
        """System info box.

        :return: the web element
        :rtype: WebElement
        """
        return get_element_by_css(
            self, "div.col-md-3:nth-child(1) > div:nth-child(1) > div:nth-child(1)"
        )

    @property
    def cpu_info_element(self) -> WebElement:
        """CPU info box.

        :return: the web element
        :rtype: WebElement
        """
        return get_element_by_css(
            self, "div.col-md-3:nth-child(2) > div:nth-child(1) > div:nth-child(1)"
        )

    @property
    def memory_info_element(self) -> WebElement:
        """Memory info box.

        :return: the web element
        :rtype: WebElement
        """
        return get_element_by_css(
            self, "div.col-md-3:nth-child(3) > div:nth-child(1) > div:nth-child(1)"
        )

    @property
    def wan_info_element(self) -> WebElement:
        """WAN info element.

        :return: the web element
        :rtype: WebElement
        """
        return get_element_by_css(
            self, "div.col-md-3:nth-child(4) > div:nth-child(1) > div:nth-child(1)"
        )
