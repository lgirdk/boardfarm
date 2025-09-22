"""Module for Selenium webdriver interaction implementations."""

from __future__ import annotations

import logging
import pathlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.remote.remote_connection import LOGGER
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.events import (
    AbstractEventListener,
    EventFiringWebDriver,
)
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.connectionpool import log

from boardfarm3.lib.utils import get_pytest_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from selenium.webdriver.remote.webdriver import WebDriver, WebElement

    from boardfarm3.templates.lan import LAN
    from boardfarm3.templates.wan import WAN
    from boardfarm3.templates.wlan import WLAN

_LOGGER = logging.getLogger(__name__)


class ScreenshotListener(AbstractEventListener):
    """Take a screenshot on exceptions/events.

    This allows to capture screenshot based on selenium web driver events.
    Capturing screenshot can be varied by setting the logging.root.level
    When logging.root.level set to :

        1. NOTSET - takes screenshots for on_exception and before_click events
        2. INFO   - takes screenshots for on_exception, before_click and
                            after_change_value_of events
        3. DEBUG  - takes screenshot for all the events
    """

    debug_enabled = logging.root.level in (logging.DEBUG, logging.INFO)
    verbose_debug_enabled = logging.root.level == logging.DEBUG

    def __init__(self, screenshot_path: str):
        """Init method.

        :param screenshot_path: the screenshot destination dir
        :type screenshot_path: str
        """
        super().__init__()
        self.screenshot_path = screenshot_path

    def capture_screenshot(
        self, driver: WebDriver, name: str, ext: str = "png"
    ) -> None:
        """Capture screenshot and save name.ext to disk.

        :param driver: web driver
        :type driver: WebDriver
        :param name: the filename (with path if needed)
        :type name: str
        :param ext: the extension, defaults to png
        :type ext: str
        """
        WebDriverWait(driver, 10).until(
            lambda drv: drv.execute_script(
                "return document.readyState",
            )
            == "complete"
        )
        now = datetime.now(tz=UTC)
        abs_path = (
            "_".join([self.screenshot_path, now.strftime("%Y%m%d_%H%M%S%f"), name])
            + "."
            + ext
        )

        def gui_page_size(dimension: str) -> str:
            return driver.execute_script(
                "return document.body.parentNode.scroll" + dimension
            )

        # Setting screen size twice because one is not enough for Selenium :)
        driver.set_window_size(gui_page_size("Width"), gui_page_size("Height"))
        driver.set_window_size(gui_page_size("Width"), gui_page_size("Height"))

        driver.get_screenshot_as_file(abs_path)
        driver.maximize_window()  # Restore window to fit screen
        _LOGGER.debug("Screenshot saved as '%s'", abs_path)

    def on_exception(
        self,
        exception: Exception,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot on exception.

        :param exception: unused
        :type exception: Exception
        :param driver: web driver
        :type driver: WebDriver
        """
        self.capture_screenshot(driver, "Exception")

    def before_navigate_to(
        self,
        url: str,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot before navigate_to event.

        :param url: unused
        :type url: str
        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "before_navigate_to")

    def after_navigate_to(
        self,
        url: str,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot after navigate_to event.

        :param url: unused
        :type url: str
        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "after_navigate_to")

    def before_click(
        self,
        element: WebElement,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot before click event.

        :param element: unused
        :type element: WebElement
        :param driver: web driver
        :type driver: WebDriver
        """
        self.capture_screenshot(driver, "before_click")

    def after_click(
        self,
        element: WebElement,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot after click event.

        :param element: unused
        :type element: WebElement
        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "after_click")

    def before_change_value_of(
        self,
        element: WebElement,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot before change_value_of event.

        :param element: unused
        :type element: WebElement
        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "before_change_value_of")

    def after_change_value_of(
        self,
        element: WebElement,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot after change_value_of event.

        :param element: unused
        :type element: WebElement
        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled or self.debug_enabled:
            self.capture_screenshot(driver, "after_change_value_of")

    def before_execute_script(
        self,
        script: str,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot before execute_script event.

        :param script: unused
        :type script: str
        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "before_execute_script")

    def after_execute_script(
        self,
        script: str,  # noqa: ARG002
        driver: WebDriver,
    ) -> None:
        """Capture screenshot after execute_script event.

        :param script: unused
        :type script: str
        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "after_execute_script")

    def before_close(self, driver: WebDriver) -> None:
        """Capture screenshot before close event.

        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "before_close")

    def after_close(self, driver: WebDriver) -> None:
        """Capture screenshot after close event.

        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "after_close")

    def before_quit(self, driver: WebDriver) -> None:
        """Capture screenshot before quit event.

        :param driver: web driver
        :type driver: WebDriver
        """
        if self.verbose_debug_enabled:
            self.capture_screenshot(driver, "before_quit")


def firefox_webproxy_driver(
    http_proxy: str, default_delay: int, headless: bool = False
) -> Firefox:
    """Initialize proxy firefox webdriver.

    :param http_proxy: proxy ip and port number
    :type http_proxy: str
    :param default_delay: selenium default delay in seconds
    :type default_delay: int
    :param headless: headless state, default to False
    :type headless: bool
    :return: gui selenium web driver instance
    :rtype: Firefox
    """
    options = Options()
    if headless:
        options.add_argument("--headless")
    if http_proxy:
        gateway_ip, port = http_proxy.split(":")
        options.set_preference("network.proxy.type", 1)
        options.set_preference("network.proxy.socks", gateway_ip)
        options.set_preference("network.proxy.socks_port", int(port))
        options.set_preference("network.proxy.socks_version", 5)
        options.set_preference("network.proxy.socks_remote_dns", True)
    options.set_preference("security.enterprise_roots.enabled", True)
    # number 2 is to save the file to the above current location instead of downloads
    options.set_preference("browser.download.folderList", 2)
    # added the download dir as /tmp
    options.set_preference("browser.download.dir", "/tmp")  # noqa: S108
    # open the file without asking any questions
    options.set_preference(
        "browser.helperApps.neverAsk.openFile",
        (
            "text/anytext,text/comma-separated-values,"
            "text/csv,application/octet-stream,text/plain"
        ),
    )
    # save the file without asking any questions
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/plain")
    options.headless = headless  # type: ignore[attr-defined]
    # Make DEBUG logs less polluted with selenium.webdriver.remote.remote_connection
    # and urllib3.connectionpool messages
    LOGGER.setLevel(logging.WARNING)
    log.setLevel(logging.WARNING)
    driver = Firefox(options=options)
    driver.implicitly_wait(default_delay)
    driver.set_page_load_timeout(default_delay)
    return driver


def get_web_driver(
    device: LAN | WAN | WLAN,
    default_delay: int,
    headless: bool = True,
) -> WebDriver:
    """Return proxy webdriver.

    Http proxy (dante) must be running on provided device.

    :param device: device instance
    :type device: LAN | WAN | WLAN
    :param default_delay: default delay in seconds
    :type default_delay: int
    :param headless: headless state, default to True
    :type headless: bool
    :return: configured Firefox webdriver instance
    :rtype: WebDriver
    """
    webdriver = firefox_webproxy_driver(
        http_proxy=device.http_proxy,
        default_delay=default_delay,
        headless=headless,
    )
    webdriver.maximize_window()
    return webdriver


class GuiHelper:
    """GuiHelper class to get webdrivers for testing."""

    _headless: bool = True

    def __init__(
        self,
        device: LAN | WAN | WLAN,
        default_delay: int = 20,
        output_dir: str | None = None,
    ) -> None:
        """GUI helper class.

        :param device: device instance
        :type device: LAN | WAN | WLAN
        :param default_delay: default delay in seconds, defaults to 20
        :type default_delay: int
        :param output_dir: output directory path, defaults to None
        :type output_dir: str | None
        """
        if output_dir is None:
            output_dir = pathlib.Path.cwd().joinpath("results").as_posix()
        self._device = device
        self._default_delay = default_delay
        self._test_name = get_pytest_name()
        self._screenshot_path = str(
            pathlib.PurePosixPath(output_dir).joinpath(self._test_name)
        )

    def get_web_driver(self) -> EventFiringWebDriver:
        """Return event firing web driver.

        :return: web driver instance
        :rtype: EventFiringWebDriver
        """
        webdriver = get_web_driver(
            self._device, self._default_delay, headless=self._headless
        )
        event_firing_webdriver = EventFiringWebDriver(
            webdriver, ScreenshotListener(self._screenshot_path)
        )
        event_firing_webdriver.screenshot_path = self._screenshot_path
        return event_firing_webdriver

    def get_webdriver_without_event_firing(self, headless: bool = True) -> WebDriver:
        """Return webdriver without the EventFiringWebDriver.

        :param headless: run in headless mode, defaults to True
        :type headless: bool
        :return: web driver instance
        :rtype: WebDriver
        """
        driver = get_web_driver(self._device, self._default_delay, headless=headless)
        driver.screenshot_path = self._screenshot_path  # type: ignore[attr-defined]
        return driver


def element_is_present_by_css(
    element_css: str,
) -> Callable[[EC.AnyDriver], WebElement | bool]:  # type: ignore[name-defined]
    """Determine if element is present by its css selector.

    :param element_css: element css selector
    :type element_css: str
    :return: True if element is present, False otherwise
    :rtype: Callable[[EC.AnyDriver], WebDriver | EventFiringWebDriver]
    """
    return EC.presence_of_element_located((By.CSS_SELECTOR, element_css))


def save_screenshot(driver: WebDriver | EventFiringWebDriver) -> None:
    """Save screenshot of the driver window.

    :param driver: webdriver instance
    :type driver: WebDriver | EventFiringWebDriver
    """
    total_width = driver.execute_script("return document.body.parentNode.scrollWidth")
    total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
    # Setting screen size twice because one is not enough for Selenium :)
    driver.set_window_size(total_width, total_height)
    driver.set_window_size(total_width, total_height)
    path = (
        "_".join(
            [
                driver.screenshot_path,  # type: ignore[union-attr]
                datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S%f"),
            ]
        )
        + "_exception.png"
    )
    driver.get_screenshot_as_file(path)


class GuiHelperNoProxy(GuiHelper):
    """GuiHelper without proxy."""

    # pylint: disable=super-init-not-called
    def __init__(
        self,
        default_delay: int = 20,
        output_dir: str | None = None,
        headless: bool = True,
    ) -> None:
        """GUI helper class without proxy.

        :param default_delay: default delay in seconds, defaults to 20
        :type default_delay: int
        :param output_dir: output directory path, defaults to None
        :type output_dir: str
        :param headless: turns on/off headless mode, defaults to True
        :type headless: bool
        """
        super().__init__(None, default_delay, output_dir)
        self._headless = headless

    def get_web_driver(self) -> EventFiringWebDriver:
        """Return event firing web driver.

        :return: web driver instance
        :rtype: EventFiringWebDriver
        """
        webdriver = firefox_webproxy_driver(
            http_proxy="",
            default_delay=self._default_delay,
            headless=self._headless,
        )
        webdriver.maximize_window()
        event_firing_webdriver = EventFiringWebDriver(
            webdriver, ScreenshotListener(self._screenshot_path)
        )
        event_firing_webdriver.screenshot_path = self._screenshot_path
        return event_firing_webdriver
