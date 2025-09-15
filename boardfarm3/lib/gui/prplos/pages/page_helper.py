"""Page Helper Module."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from boardfarm3.lib.gui.gui_helper import (
    element_is_present_by_css,
    save_screenshot,
)
from boardfarm3.lib.gui.prplos.pages.login import LoginPage  # pylint: disable=C0415

if TYPE_CHECKING:
    from ipaddress import IPv4Address

    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support.events import EventFiringWebDriver


PRPLOS_USER = "admin"
PRPLOS_PASSWORD = "admin"  # noqa: S105  # super secret!!!!


def get_element_by_css(page: Any, element: str) -> WebElement:  # noqa: ANN401
    """Get an element by CSS selector (wait if needed).

    :param page: the webpage
    :type page: Any
    :param element: the element
    :type element: str
    :raises NoSuchElementException: if the element is not found
    :return: the web element
    :rtype: WebElement
    """
    if page.wait.until(element_is_present_by_css(element)):
        return page.driver.find_element(by=By.CSS_SELECTOR, value=element)
    msg = f"{element} not found in {page.driver.current_url}"
    raise NoSuchElementException(msg)


def wait_until_loaded(page: Any, timeout: int | None = None) -> bool:  # noqa: ANN401
    """Wait until the page is loaded completely.

    Generic method to wait upto fluent_wait time or upto timeout specified
    by the user until the page is loaded and return the status

    :param page: the page obj
    :type page: Any
    :param timeout: timeout in seconds to load the page, defaults to None
    :type timeout: int | None
    :return: True if page is loaded
    :rtype: bool
    """
    if not timeout:
        timeout = page.fluent_wait
    timeout = int(time.time()) + timeout
    output = False
    while int(time.time()) <= timeout and not output:
        try:
            output = page.is_page_loaded(page.driver)  # pylint: disable=E1111
        except (  # noqa: PERF203
            NoSuchElementException,
            TimeoutException,
            StaleElementReferenceException,
        ):
            output = False
    if not output:
        save_screenshot(page.driver)
    return output


def initialize(  # noqa: PLR0913
    page: Any,  # noqa: ANN401
    driver: WebDriver | EventFiringWebDriver,
    gw_ip: str | IPv4Address,
    fluent_wait: int = 20,
    use_https: bool = False,
    user: str = PRPLOS_USER,
    password: str = PRPLOS_PASSWORD,
) -> None:
    """Initialize the page obj.

    :param page: the page
    :type page: Any
    :param driver: the web driver
    :type driver: WebDriver | EventFiringWebDriver
    :param gw_ip: the gateway ip
    :type gw_ip: str | IPv4Address
    :param fluent_wait: browser fluent wait, defaults to 20
    :type fluent_wait: int
    :param use_https: use htpp/s, defaults to False
    :type use_https: bool
    :param user: username, defaults to admin
    :type user: str
    :param password: login password, defaults to admin
    :type password: str
    """
    page.driver = driver
    page.wait = WebDriverWait(
        driver=page.driver,  # type: ignore[type-var]
        timeout=fluent_wait,
    )
    page.actions = ActionChains(
        driver if isinstance(driver, WebDriver) else driver.wrapped_driver
    )
    page.fluent_wait = fluent_wait
    if str(gw_ip) not in page.driver.current_url:
        page.driver.get(f"https://{gw_ip}" if use_https else f"http://{gw_ip}")
    driver.set_page_load_timeout(fluent_wait * 4)
    if not isinstance(page, LoginPage):
        loginpage = LoginPage(page.driver, gw_ip)
        wait_until_loaded(loginpage)
        loginpage.login(user, password)
        return

    page.wait.until(page.is_page_loaded)
