# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

from selenium.webdriver.support.select import Select
from selenium.common.exceptions import NoSuchElementException
import time

def enter_input(web_gui, input_path, input_value):
    try:
        # enter input value in text box for web page
        input_tab = web_gui.find_element_by_id(input_path)
        input_tab.clear()
        input_tab.send_keys(input_value)
        return True
    except NoSuchElementException:
        return False

def click_button_id(web_gui, clickbutton):
    try:
        # to click any button using id
        click_tab = web_gui.find_element_by_id(clickbutton)
        click_tab.click()
        time.sleep(5)
        return True
    except NoSuchElementException:
        return False

def click_button_xpath(web_gui, clickbutton):
    try:
        # to click any button using xpath
        click_tab = web_gui.find_element_by_xpath(clickbutton)
        click_tab.click()
        time.sleep(5)
        return True
    except NoSuchElementException:
        return False

def select_option_by_id(web_gui, select_button, select_value):
    try:
        # To select the option required
        select = Select(web_gui.find_element_by_id(select_button))
        select.select_by_visible_text(select_value)
        time.sleep(5)
        return select
    except NoSuchElementException:
        return None

def select_option_by_name(web_gui, select_button, select_value):
    try:
        # To select the option required
        select = Select(web_gui.find_element_by_name(select_button))
        select.select_by_visible_text(select_value)
        time.sleep(5)
        return select
    except NoSuchElementException:
        return None

def select_option_by_xpath(web_gui, select_button, select_value):
    try:
        # To select the option required
        select = Select(web_gui.find_element_by_xpath(select_button))
        select.select_by_visible_text(select_value)
        time.sleep(5)
        return select
    except NoSuchElementException:
        return None

def get_drop_down_value(web_gui, get_value):
    try:
        # To get the value which already exists
        select = Select(web_gui.find_element_by_id(get_value))
        selected_option = select.first_selected_option
        selected_value = selected_option.text
        return selected_value
    except NoSuchElementException:
        return None

def get_radio_button_value(web_gui, get_value):
    try:
        # To get radio button value
        radio_button = web_gui.find_elements_by_id(get_value)
        for radiobutton in radio_button:
            radio = radiobutton.get_attribute('src')
            if "radio-box-checked" in radio:
                return True
            else:
                return False
    except NoSuchElementException:
        return None

def get_text_value(web_gui, get_value):
    try:
        # To get the text box value
        text_button = web_gui.find_element_by_id(get_value)
        text_value = text_button.text
        return text_value
    except NoSuchElementException:
        return None

def get_text_value_by_xpath(web_gui, get_value):
    try:
        # To get the text box value
        text_button = web_gui.find_element_by_xpath(get_value)
        text_value = text_button.text
        return text_value
    except NoSuchElementException:
        return None

def get_value_from_disabled_input(web_gui, get_value):
    # To get the text with dynamic value
    js = "return document.getElementById(\"{!s}\").value;".format(str(get_value))
    text_value = web_gui.execute_script(js)
    return str(text_value)

def get_icon_check_value_by_id(web_gui, get_value):
    try:
        # To get icon button value
        icon_button = web_gui.find_elements_by_id(get_value)
        for iconbutton in icon_button:
            icon = iconbutton.get_attribute('src')
            if "icon-check.svg" in icon:
                return True
            else:
                return False
    except NoSuchElementException:
        return None

def get_icon_check_value_by_xpath(web_gui, get_value):
    try:
        # To get icon button value
        icon_button = web_gui.find_elements_by_xpath(get_value)
        for iconbutton in icon_button:
            icon = iconbutton.get_attribute('src')
            if "icon-check.svg" in icon:
                return True
            else:
                return False
    except NoSuchElementException:
        return None

def check_element_is_enable_by_id(web_gui, check_value):
    try:
        text_button = web_gui.find_element_by_id(check_value)
        text_value = text_button.is_enabled()
        return text_value
    except NoSuchElementException:
        return None

def get_check_box_value_by_id(web_gui, get_value):
    try:
        # To get icon button value
        box_button = web_gui.find_elements_by_id(get_value)
        for boxbutton in box_button:
            box = boxbutton.get_attribute('src')
            if "check-box-checked.png" in box or 'radio-box-checked.png' in box:
                return True
            else:
                return False
    except NoSuchElementException:
        return None

def get_check_box_value_by_xpath(web_gui, get_value):
    try:
        # To get icon button value
        box_button = web_gui.find_elements_by_xpath(get_value)
        for boxbutton in box_button:
            box = boxbutton.get_attribute('src')
            if "check-box-checked.png" in box or 'radio-box-checked.png' in box:
                return True
            else:
                return False
    except NoSuchElementException:
        return None
