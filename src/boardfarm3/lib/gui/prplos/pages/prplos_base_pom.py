"""PrplOS Base Page Oobject Module (POM)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from selenium.common.exceptions import TimeoutException

from boardfarm3.lib.gui.prplos.pages.page_helper import (
    get_element_by_css,
    initialize,
    wait_until_loaded,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ipaddress import IPv4Address

    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support.events import EventFiringWebDriver
    from selenium.webdriver.support.ui import WebDriverWait


class PrplOSBasePOM:
    """Contains objects that are common to all the pages of the PrplOS GUI."""

    driver: WebDriver | EventFiringWebDriver
    wait: Any | WebDriverWait
    action: ActionChains

    def __init__(
        self,
        driver: WebDriver | EventFiringWebDriver,
        gw_ip: str | IPv4Address,
        fluent_wait: int = 20,
        use_https: bool = False,
    ) -> None:
        """Initialize the class.

        :param driver: webdriver instance
        :type driver: Union[WebDriver, EventFiringWebDriver]
        :param gw_ip: gateway ip address
        :type gw_ip: Union[str, IPv4Address]
        :param fluent_wait: timeout in seconds to load the page, defaults to 20
        :type fluent_wait: int
        :param use_https: flag to specify whether http or https, defaults to false
        :type use_https: bool
        """
        initialize(
            page=self,
            driver=driver,
            gw_ip=gw_ip,
            fluent_wait=fluent_wait,
            use_https=use_https,
        )

    def __getattribute__(self, name: str) -> None:
        """Take a screenshot and save to a folder upon TimeoutException.

        :param name: the attribute
        :type name: str
        :return: the attribute value
        :rtype: related to the attribute
        :raises TimeoutException: if the attr was not found
        """
        try:
            return super().__getattribute__(name)
        except TimeoutException:
            now = datetime.now(UTC)
            sc_path = (
                "_".join(
                    [
                        self.driver.screenshot_path,  # type: ignore[union-attr]
                        now.strftime("%Y%m%d_%H%M%S%f"),
                    ],
                )
                + "_TimeoutException.png"
            )
            self.driver.get_screenshot_as_file(sc_path)
            _LOGGER.debug("Screenshot saved as '%s'", sc_path)
            raise

    def wait_until_loaded(self, timeout: int | None = None) -> bool:
        """Wait until the page is loaded completely.

        Generic method to wait upto fluent_wait time or upto timeout specified
        by the user until the page is loaded and return the status

        :param timeout: timeout in seconds to load the page, defaults to None
        :type timeout: int | None, default None
        :return: True if page is loaded, Otherwise False
        :rtype: bool
        """
        return wait_until_loaded(self, timeout)

    def is_page_loaded(
        self,
        _driver: WebDriver | EventFiringWebDriver,
    ) -> bool:
        """Verify the page is completely loaded.

        Must be overridden  in the derived class!

        :raises AttributeError: if not overriden
        """
        msg = "is_page_loaded must be defined in derived class"
        raise AttributeError(msg)

    def click_networking_submenu(self, element: WebElement) -> None:
        """Ckick on WAN menu option.

        :param element: the element to click
        :type element: WebElement
        """
        self.actions.move_to_element(  # type: ignore[attr-defined]
            element,
        ).pause(1).click().perform()
        time.sleep(1)

    def logout(self) -> None:
        """Log out.

        All the pages derived from the POM have logged in!
        """
        get_element_by_css(self, ".btn").click()
        get_element_by_css(self, ".logo")
