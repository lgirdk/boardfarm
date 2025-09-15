"""Login Page POM."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from boardfarm3.lib.gui.gui_helper import element_is_present_by_css

if TYPE_CHECKING:
    from ipaddress import IPv4Address

    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support.events import EventFiringWebDriver


def _get_element_by_css(page: Any, element: str) -> WebElement:  # noqa: ANN401
    if page.wait.until(element_is_present_by_css(element)):
        return page.driver.find_element(by=By.CSS_SELECTOR, value=element)
    msg = f"{element} not found in {page.driver.current_url}"
    raise NoSuchElementException(msg)


class LoginPage:
    """Page Object for Login page."""

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
        """Initialize LoginPage POM.

        :param driver: webdriver instance
        :type driver: WebDriver | EventFiringWebDriver
        :param gw_ip: gateway ip address
        :type gw_ip: str | IPv4Address
        :param fluent_wait: timeout in seconds to load the page, defaults to 20
        :type fluent_wait: int
        :param use_https: whether to use http/s, defaults to False
        :type use_https: bool
        """
        self.driver = driver
        self.wait = WebDriverWait(
            driver=self.driver,  # type: ignore[type-var]
            timeout=fluent_wait,
        )
        self.actions = ActionChains(
            driver if isinstance(driver, WebDriver) else driver.wrapped_driver
        )
        self.fluent_wait = fluent_wait
        if str(gw_ip) not in self.driver.current_url:
            self.driver.get(f"https://{gw_ip}" if use_https else f"http://{gw_ip}")
        driver.set_page_load_timeout(fluent_wait * 4)  # type: ignore[union-attr]
        self.wait.until(self.is_page_loaded)

    def is_page_loaded(self, driver: WebDriver | EventFiringWebDriver) -> bool:
        """Verify the home page is completely loaded.

        :param driver: webdriver instance
        :type driver: WebDriver | EventFiringWebDriver
        :return: True if home page is loaded, Otherwise False
        :rtype: bool
        """
        return (
            self.logo_element.is_displayed()
            and self.username_box_element.is_displayed()
            and self.password_box_element.is_displayed()
            and driver.execute_script("return document.readyState == 'complete'")
        )

    @property
    def logo_element(self) -> WebElement:
        """Logo element.

        :return: The web element
        :rtype: WebElement
        """
        return _get_element_by_css(self, ".logo")

    @property
    def username_box_element(self) -> WebElement:
        """Username textbox element.

        :return: The web element
        :rtype: WebElement
        """
        return _get_element_by_css(self, "#identification")

    @property
    def password_box_element(self) -> WebElement:
        """Password textbox element.

        :return: The web element
        :rtype: WebElement
        """
        return _get_element_by_css(self, "#password")

    def _wait_until_logged_in(self) -> None:
        # waits for the logout button to appear
        _get_element_by_css(self, ".btn")

    def login(self, user: str, password: str) -> None:
        """Login to the UI.

        Login to the UI or if the UI is not at the Login page then performs
        first installation operation

        :param user: login username
        :type user: str
        :param password: login password
        :type password: str
        """
        self.username_box_element.send_keys(user)
        self.username_box_element.send_keys(Keys.ENTER)
        self.password_box_element.send_keys(password)
        self.password_box_element.send_keys(Keys.ENTER)
        self._wait_until_logged_in()
