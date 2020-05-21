# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import time
import traceback

from pyvirtualdisplay import Display
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from xvfbwrapper import Xvfb

from .common import get_webproxy_driver, resolv_dict
from .gui_helper import (click_button_id, enter_input, get_drop_down_value,
                         get_radio_button_value, get_text_value,
                         select_option_by_id)


class web_gui:
    """Webgui lib."""

    prefix = ""

    def __init__(self,
                 output_dir=os.path.join(os.getcwd(), "results"),
                 **kwargs):
        """Instance initialisation.
        To set the path for saving the gui page screenshots
        To set the driver and display port as None for gui
        initialisation
        """
        self.output_dir = output_dir
        self.default_delay = 30
        self.driver = None
        self.display = None

    # this specified a prefix for the screenshots file names
    # it cna be used to prepend the testcase name to the file name
    def set_prefix(self, prefix=""):
        """Specifying a prefix for the screenshots file name.

        :param prefix - prefix string
        :type prefix - string
        """
        self.prefix = prefix

    def _save_screenshot(self, name):
        """Save screenshot of the selenium web gui driver.
        and save it in the current working directory of the os path.

        :param name: name for saving scrrenshot
        :type name: string
        :return: full path of the file
        :rtype: string
        """
        full_path = os.path.join(self.output_dir, name)
        self.driver.save_screenshot(full_path)
        return full_path

    def enter_input_value(self, key_id, input_value):
        """Enter_input_value method to Enter input value in a text box.

        :param key_id: id of the gui element
        :type key_id: string
        :param input_value: input text
        :type input_value: string
        :raises assertion: Unable to enter value
        """
        key_value = self.key[key_id]
        select_value = resolv_dict(self.config, key_value)
        self.scroll_view(select_value)
        enter_value = enter_input(self.driver, select_value, input_value)
        assert enter_value, "Unable to enter value %s" % input_value

    def get_text(self, value):
        """To get the text from the text box in a gui page.

        :param value: text value
        :type value: string
        :return: text to be captured
        :rtype: string
        """
        key_value = self.key[value]
        key_value = eval("self.config" + key_value)
        text = get_text_value(self.driver, key_value)
        return text

    def click_button(self, key_id):
        """Click_button method to click button in gui page.

        :param key_id: id of the gui element
        :type key_id: string
        :raises assertion: Click button
        """
        select_id = self.key[key_id]
        select_key_value = resolv_dict(self.config, select_id)
        self.scroll_view(select_key_value)
        Click_button = click_button_id(self.driver, select_key_value)
        assert Click_button is True, "Click button : %s  " % Click_button

    def selected_option_by_id(self, key_id, value):
        """Select option in the dropdown by id.

        :param key_id: id of the gui element
        :type key_id: string
        :param value: element value
        :type value: string
        :raises assertion: Selecting dropdwon button
        """
        select_id = self.key[key_id]
        select_key_value = resolv_dict(self.config, select_id)
        self.scroll_view(select_key_value)
        select_button = select_option_by_id(self.driver, select_key_value,
                                            value)
        assert select_button, "Select button : %s  " % select_button

    def verify_radio(self, value):
        """Verify radio button in gui page.

        :param value: radio id
        :type value: string
        :raises assertion: Changes are not applied properly
        """
        key_value = self.key[value]
        key_value = resolv_dict(self.config, key_value)
        key_value = get_radio_button_value(self.driver, key_value)
        assert key_value, "Changes are not applied properly"

    def verify_drop_down(self, value, check_value):
        """Verify check value.
         Is present in the dropdown of the gui page.

        :param value: dropdown id
        :type value: string
        :param check_value: check value from the dropdown
        :type check_value: string
        :return: True or False
        :rtype: boolean
        """
        key_value = self.key[value]
        key_value = resolv_dict(self.config, key_value)
        keyvalue = get_drop_down_value(self.driver, key_value)
        if keyvalue == check_value:
            return True
        else:
            return False

    def verify_text(self, value, text):
        """Verify text value in gui page.

        :param value: element id
        :type value: string
        :param text: text to be verified
        :type text: string
        """
        key_value = self.key[value]
        key_value = resolv_dict(self.config, key_value)
        key_value = get_text_value(self.driver, key_value)
        if key_value == text:
            return True
        else:
            return False

    def scroll_view(self, scroll_value):
        """Scrolling into the particular option for better view.

        :param scroll_value: gui element
        :type scroll_value: string
        """
        self.driver.execute_script(
            "arguments[0].scrollIntoView();",
            self.driver.find_element_by_id(scroll_value),
        )

    def _enter_text(self, txt_box, txt):
        """To enter the value in the text box.

        :param txt_box: id of the text box
        :type txt_box: string
        :param txt: text to be entered
        :type txt: string
        """
        txt_list = list(txt)
        for c in txt_list:
            time.sleep(0.1)
            txt_box.send_keys(c)

    def check_element_visibility(self, *element, **kwargs):
        """To check the visibility of the element on the page.

        :param element: id or name
        :type element: string
        :param kwargs: element
        :type kwargs: string
        :return: Web driver query output
        """
        """ex. *element=('id, 'element') or ('name, 'element')"""
        timeout = kwargs.get("timeout", self.default_delay)
        query = None
        try:
            query = WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located(element))
        except Exception:
            print(
                "check_element_visibility(%s, %s): timeout to find element\n" %
                element)
        return query

    def check_element_clickable(self, *element, **kwargs):
        """To check the element is clickable on the page.

        :param element: id or name
        :type element: string
        :param kwargs: element
        :type kwargs: string
        :return: Web driver query output
        """
        timeout = kwargs.get("timeout", self.default_delay)
        query = None
        try:
            query = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable(element))
        except Exception:
            print(
                "check_element_clickable(%s, %s): timeout to find element\n" %
                element)
        return query

    def check_element_selection_state_to_be(self, *element, **kwargs):
        """To check the element selection state on the page.

        :param element: id or name
        :type element: string
        :param kwargs: element
        :type kwargs: string
        :return: Web driver query output
        """
        timeout = kwargs.get("timeout", self.default_delay)
        query = None
        try:
            query = WebDriverWait(self.driver, timeout).until(
                EC.element_selection_state_to_be(element))
        except Exception:
            print(
                "check_element_selection_state_to_be(%s, %s): timeout to find element\n"
                % element)
        return query

    def wait_for_element(self, index_by="id", ele_index=None):
        """Wait for element on the page.

        :param index_id: 'id', defaults by id
        :type index_id: string, optional
        :param ele_index: gui element id, defaults by None
        :type ele_index: string, optional
        :raises assertion: check_element_visibility
        """
        assert ele_index is not None, "ele_index=None"
        if index_by == "name":
            by = By.NAME
        else:
            by = By.ID

        self.driver.implicitly_wait(self.default_delay)

        print("wait_for_element(): check_element_visibility(%s, %s)" %
              (str(by), ele_index))
        ele = self.check_element_visibility(by, ele_index)
        assert ele is not None, "check_element_visibility(%s, %s)=False" % (
            str(by),
            ele_index,
        )

    def check_element_exists(self, text):
        """To check if the elements exist in the gui page by xpath.

        :param text: xpath of the element
        :type text: string
        :raises exception: If element not found
        :return: Element or None
        :rtype: string
        """
        try:
            element = self.driver.find_element_by_xpath(text)
            print("Element '" + text + "' found")
            return element
        except NoSuchElementException:
            print("check_element_exists No element '" + text + "' found")
            return None

    def check_element_exists_by_name(self, text):
        """To check if the elements exist in the gui page by name.

        :param text: name of the element
        :type text: string
        :raises exception: If element not found
        :return: Element or None
        :rtype: string
        """
        try:
            element = self.driver.find_element_by_name(text)
            print("Element '" + text + "' found")
            return element
        except NoSuchElementException:
            print("No element '" + text + "' found")
            return None

    def wait_for_redirects(self):
        """Wait for possible redirects to settle down in gui page."""
        # wait for possible redirects to settle down
        url = self.driver.current_url
        for _ in range(10):
            time.sleep(5)
            if url == self.driver.current_url:
                break
            url = self.driver.current_url

    def gui_logout(self, id_value):
        """Logout of the gui page.

        :param id_value: element id for logout
        :type id_value: string
        :raises exception: If element not found returns None
        :return: True or False
        :rtype: boolean
        """
        try:
            ele_botton = self.check_element_clickable(By.ID,
                                                      id_value,
                                                      timeout=3)
            if ele_botton is not None:
                ele_botton.click()
                print("Logout clicked")
            return True
        except NoSuchElementException:
            print("No logout botton element ('id', %s) found " % id_value)
            return False

    def driver_close(self, logout_id):
        """Logout of the gui page and close selenium web driver.

        :param logout_id: element id for logout
        :type logout_id: string
        """
        self.gui_logout(logout_id)
        self.driver.quit()
        print("driver quit")
        if self.display is not None:
            self.display.stop()
            print("display stop")

    # Starts the python wrapper for Xvfb, Xephyr and Xvnc
    # the backend can be set via BFT_OPTIONS
    def open_display(self):
        """Display of the gui page after connecting through some random port."""
        from pyvirtualdisplay.randomize import Randomizer
        from boardfarm import config

        if config.default_headless:
            self.display = None
            return

        if config.default_display_backend == "xvnc":
            xc, yc = config.default_display_backend_size.split("x")
            x = int(xc)
            y = int(yc)
            r = Randomizer(
            ) if config.default_display_backend_port == 0 else None
            self.display = Display(
                backend=config.default_display_backend,
                rfbport=config.default_display_backend_port,
                rfbauth=os.environ["HOME"] + "/.vnc/passwd",
                visible=0,
                randomizer=r,
                size=(x, y),
            )

        elif config.default_display_backend == "xvfb":
            self.display = Xvfb()
        else:
            raise Exception("backend not yet tested!")

        self.display.start()

    def get_web_driver(self, proxy):
        """Get web driver using proxy.

        :param proxy: proxy value of lan or wan, it can be obtained using
                      the method get_proxy(device)
        :type proxy:  web driver proxy
        :raises Exception: Failed to get webproxy driver via proxy
        :return: web driver
        :rtype: web driver element
        """
        from boardfarm import config

        try:
            self.driver = get_webproxy_driver(proxy, config)
        except Exception:
            traceback.print_exc()
            raise Exception("Failed to get webproxy driver via proxy " + proxy)
        return self.driver

    def botton_click_to_next_page(self, index_by="id", ele_index=None):
        """Click button and verify.

        :param index_by: 'id' or 'name'
        :type index_by: string
        :raises assertion: Assert if element index is None
        :param ele_index: element index
        :type ele_index: string
        """
        assert ele_index is not None, "ele_index=None"
        if index_by == "name":
            by = By.NAME
        else:
            by = By.ID

        # verify $botton is exist
        botton = self.check_element_visibility(by, ele_index)
        assert botton is not None, "timeout: not found %s in page" % ele_index
        print("get botton value: %s" % botton.get_attribute("value"))

        self._save_screenshot("%s_click.png" % ele_index)
        self.check_element_clickable(by, ele_index).click()

    def home_page(self, page_id):
        """Check the home page of the gui page.

        :param page_id: id of the gui element
        :type page_id: string
        :raises assertion: timeout: not found home page
        """
        home_page = self.check_element_visibility(By.ID, page_id)
        # wait for possible redirects to settle down
        self.wait_for_redirects()
        time.sleep(10)
        assert home_page is not None, "timeout: not found home page"
        print(home_page.text)
        self._save_screenshot(self.prefix + "home_page.png")

    def navigate_to_target_page(self, navi_path):
        """Navigating to teh target page.

        :param navi_path: navigation path of the page
        :type navi_path: string
        :raises assertion: Error in click
        """
        for path in navi_path:
            temp = self.key[path]
            temp = resolv_dict(self.config, temp)
            button = click_button_id(self.driver, temp)
            assert button, "Error in click %s" % path
            print("Click %s : PASS" % path)
            time.sleep(2)

    def __del__(self):
        """Destructor method.
        Deletes the webgui object.
        The function is called when the object references have gone.
        """
        try:
            self.display.stop()
        except Exception:
            pass
