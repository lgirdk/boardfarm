"""Visual regression test for prplOS Login Page."""

from typing import Any, Callable

import pytest
from selenium.webdriver.firefox.webdriver import WebDriver

from boardfarm3.lib.gui.prplos.pages.login import LoginPage


@pytest.mark.env_req({"environment_def": {"board": {"model": "prplOS"}}})
def test_login_page(
    browser_data_visual_regression: tuple[WebDriver, Any],
    check: Callable,
) -> None:
    """Login Page.

    # noqa: DAR101
    """
    driver, gw_ip = browser_data_visual_regression
    LoginPage(driver, gw_ip)
    assert check(driver, "Login page")  # noqa: S101
