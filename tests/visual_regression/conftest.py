"""Pytest contest module."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Callable

import pytest
from selenium.webdriver.common.by import By

from boardfarm3.lib.gui.gui_helper import GuiHelper
from boardfarm3.templates.cpe import CPE
from boardfarm3.templates.lan import LAN
from boardfarm3.use_cases.image_comparison import compare_images

if TYPE_CHECKING:
    from collections.abc import Generator

    from _pytest.fixtures import FixtureRequest
    from selenium.webdriver.firefox.webdriver import WebDriver

    from boardfarm3.lib.device_manager import DeviceManager

_LOGGER = logging.getLogger(__name__)

_RESOURCES = f"{Path(__file__).parent}/resources/"


class TestDetails:
    """TestDetails helper class."""

    def __init__(self) -> None:
        """Test details helper class."""
        self.test_name = ""
        self.saved = False


@pytest.fixture(scope="session")
def get_output_dir(request: FixtureRequest) -> str:
    """Fixture to get the output dir from cmd line.

    :param request: a pytest helper fixture
    :type request: FixtureRequest
    :return: the results directory
    :rtype: str
    """
    return request.config.getoption("--save-console-logs")


@pytest.fixture
def get_test_data() -> TestDetails:
    """Fixture for getting all test data.

    :return: the test details
    :rtype: TestDetails
    """
    return TestDetails()


@pytest.fixture
def browser_data_visual_regression(
    device_manager: DeviceManager,
    get_output_dir: str,
    get_test_data: TestDetails,
) -> Generator:
    """Fixture for the VisReg.

    :param device_manager: the device manager fixture
    :type device_manager: DeviceManager
    :param get_output_dir: the results directory path
    :type get_output_dir: str
    :param get_test_data: test context holder
    :type get_test_data: TestDetails
    :raises RuntimeError: _if a screenshot is saved (i.e. in the very first run)
    :yield: the driver, gateway ip
    :rtype: Generator
    """
    cpe = device_manager.get_device_by_type(CPE)  # type: ignore[type-abstract]
    lan = device_manager.get_device_by_type(LAN)  # type: ignore[type-abstract]
    driver = GuiHelper(
        lan, output_dir=get_output_dir
    ).get_webdriver_without_event_firing()
    gw_ip = cpe.sw.lan_gateway_ipv4

    yield driver, gw_ip

    driver.quit()
    test_details = get_test_data
    if test_details.saved:
        msg = "This test saved an attachment."
        _LOGGER.critical(msg)
        raise RuntimeError(msg)


def _remove_elements(driver: WebDriver, elements_str: list[str]) -> None:
    # remove the given elements from the page
    for selector in elements_str:
        driver.execute_script(f"""
        var element = document.querySelector("{selector}");
        if (element)
            element.parentNode.removeChild(element);
        """)  # type: ignore[no-untyped-call]


def _get_areas_from_elements(
    driver: WebDriver, elements_str: list[str]
) -> list[tuple[int, int, int, int]]:
    ignore: list[tuple[int, int, int, int]] = []
    for selector in elements_str:
        element = driver.find_element(By.CSS_SELECTOR, selector)
        ignore.append(
            (
                element.location["x"],
                element.location["y"],
                element.location["x"] + int(element.size["width"]),
                element.location["y"] + int(element.size["height"]),
            )
        )
    return ignore


@pytest.fixture
def check(  # noqa: C901
    get_test_data: TestDetails,
    record_property: Callable,
) -> bool:
    """Fixture to check the page.

    :param get_test_data: context holder
    :type get_test_data: TestDetails
    :param record_property: store images for future use by the html report
    :type record_property: Callable
    :return: True if the 2 images are identical
    :rtype: bool
    """

    def _compare(  # noqa: C901, PLR0912, PLR0913
        driver: WebDriver,
        # page: BasePOM | LoginPage,
        name: str,
        ignore: list[tuple[int, int, int, int]] | list[str] | None = None,
        remove: list[str] | None = None,
        full_screenshot: bool = True,
        delay_screenshot: int = 3,
    ) -> bool:
        ignore = [] if ignore is None else ignore
        test_details = get_test_data
        original = f"{name}.png"
        reource_path = (
            Path(_RESOURCES)
            .joinpath(Path(driver.screenshot_path).name)  # type: ignore[attr-defined]
            .joinpath(original)
        )
        current = f"{name}_current.png"
        dir_path = Path(driver.screenshot_path)  # type: ignore[attr-defined]
        dir_path.mkdir(exist_ok=True)
        sleep(delay_screenshot)
        if remove:
            _remove_elements(driver, remove)  # type: ignore[arg-type]

        if full_screenshot:
            driver.save_full_page_screenshot(
                dir_path.joinpath(current).as_posix(),
            )
        else:
            driver.save_screenshot(
                dir_path.joinpath(current).as_posix(),
            )

        result = False
        mask_areas = []

        if reource_path.exists():
            shutil.copy(
                reource_path.as_posix(),
                dir_path.joinpath(Path(original)).as_posix(),
            )
        else:
            dir_path.joinpath(Path(current)).rename(
                dir_path.joinpath(Path(original)),
            )
            reource_path.parent.mkdir(exist_ok=True)
            shutil.copy(
                dir_path.joinpath(Path(original)).as_posix(),
                reource_path.parent.as_posix(),
            )
            test_details.saved = True
            return test_details.saved

        if ignore and isinstance(ignore[0], str):
            mask_areas = _get_areas_from_elements(
                driver,
                ignore,  # type: ignore[arg-type]
            )
        else:
            mask_areas = ignore  # type: ignore[assignment]

        try:
            result = (
                compare_images(
                    Path(f"{dir_path}/{original}"),
                    Path(f"{dir_path}/{current}"),
                    mask_areas,
                )
                == 100.0  # noqa: PLR2004
            )
        except ValueError as val_err:  # pylint: disable=broad-except
            msg = "Input images must have the same dimensions"
            if msg in str(val_err):
                _LOGGER.exception(msg)
                result = False
            else:
                raise

        if not result:
            for image in [
                Path(f"{dir_path}/{original}"),
                Path(f"{dir_path}/{current}"),
            ]:
                record_property(
                    image.name,
                    Path(
                        *image.parts[
                            image.parts.index(
                                Path(
                                    driver.screenshot_path,  # type: ignore[attr-defined]
                                ).name
                            ) :
                        ]
                    ).as_posix(),
                )
        for image in dir_path.glob("*.png"):
            if "masked" in image.name or "contour" in image.name:
                # this is a little messy, to be cleaned up
                record_property(
                    image.name,
                    Path(
                        *image.parts[
                            image.parts.index(
                                Path(
                                    driver.screenshot_path,  # type: ignore[attr-defined]
                                ).name
                            ) :
                        ]
                    ).as_posix(),
                )

        return result

    return _compare  # type: ignore[return-value]
