"""Visual regression test for prplOS Home Page."""

from typing import Any, Callable

import pytest
from selenium.webdriver.firefox.webdriver import WebDriver

from boardfarm3.lib.gui.pages.home import HomePage


@pytest.mark.env_req({"environment_def": {"board": {"model": "prplOS"}}})
def test_home_page_fail(
    browser_data_visual_regression: tuple[WebDriver, Any],
    check: Callable,
) -> None:
    """Login Page.

    # noqa: DAR101
    """
    driver, gw_ip = browser_data_visual_regression
    HomePage(driver, gw_ip)
    assert check(driver, "Home page")  # noqa: S101
