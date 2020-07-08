# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import time

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.select import Select


def enter_input(web_gui, input_path, input_value):
    """To enter the text box value in web page.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param input_path: element id of particular box
    :type input_path: string
    :param input_value: text box value to be enter
    :type input_value: string
    :raises Exception: If error thrown returns False
    :return: True
    :rtype: boolean
    """
    try:
        input_tab = web_gui.find_element_by_id(input_path)
        input_tab.clear()
        input_tab.send_keys(input_value)
        return True
    except NoSuchElementException:
        return False


def click_button_id(web_gui, clickbutton):
    """To click the button using the element id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param clickbutton: web element id of the button
    :type clickbutton: string
    :raises Exception: If error thrown returns False
    :return: True
    :rtype: boolean
    """
    try:
        click_tab = web_gui.find_element_by_id(clickbutton)
        click_tab.click()
        time.sleep(5)
        return True
    except NoSuchElementException:
        return False


def click_button_xpath(web_gui, clickbutton):
    """To click the page button using the xpath.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param clickbutton: web element id of the button
    :type clickbutton: string
    :raises Exception: If error thrown returns False
    :return: True
    :rtype: boolean
    """
    try:
        click_tab = web_gui.find_element_by_xpath(clickbutton)
        click_tab.click()
        time.sleep(5)
        return True
    except NoSuchElementException:
        return False


def select_option_by_id(web_gui, select_button, select_value):
    """To select the option from drop down using id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param select_button: web element id of drop down
    :type select_button: string
    :param select_value: value to be selected
    :type select_value: string
    :raises Exception: If error thrown returns False
    :return: value to be chosen
    :rtype: string
    """
    try:
        select = Select(web_gui.find_element_by_id(select_button))
        select.select_by_visible_text(select_value)
        time.sleep(5)
        return select
    except NoSuchElementException:
        return None


def select_option_by_name(web_gui, select_button, select_value):
    """To select the option from drop down using element name.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param select_button: web element id of drop down
    :type select_button: string
    :param select_value: value to be selected
    :type select_value: string
    :raises Exception: If error thrown returns None
    :return: value to be chosen
    :rtype: string
    """
    try:
        select = Select(web_gui.find_element_by_name(select_button))
        select.select_by_visible_text(select_value)
        time.sleep(5)
        return select
    except NoSuchElementException:
        return None


def select_option_by_xpath(web_gui, select_button, select_value):
    """To select the option from drop down using xpath.

    :param web_gui : web driver after initializing page
    :type web_gui : string
    :param select_button : web element id of drop down
    :type select_button : string
    :param select_value : value to be selected
    :type select_value : string
    :raises Exception : If error thrown returns None
    :return : value to be chosen
    :rtype : string
    """
    try:
        select = Select(web_gui.find_element_by_xpath(select_button))
        select.select_by_visible_text(select_value)
        time.sleep(5)
        return select
    except NoSuchElementException:
        return None


def get_drop_down_value(web_gui, get_value):
    """To get the drop down value using id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: text value to check whether it exists in drop down
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: value to be chosen
    :rtype: string
    """
    try:
        select = Select(web_gui.find_element_by_id(get_value))
        selected_option = select.first_selected_option
        selected_value = selected_option.text
        return selected_value
    except NoSuchElementException:
        return None


def get_radio_button_value(web_gui, get_value):
    """To get the radio button status whether chosen or not.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for the radio button
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: True or False
    :rtype: boolean
    """
    try:
        radio_button = web_gui.find_elements_by_id(get_value)
        for radiobutton in radio_button:
            radio = radiobutton.get_attribute("src")
            if "radio-box-checked" in radio:
                return True
            else:
                return False
    except NoSuchElementException:
        return None


def get_text_value(web_gui, get_value):
    """To get the radio button status whether chosen or not.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for the radio button
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: True or False
    :rtype: boolean
    """
    try:
        text_button = web_gui.find_element_by_id(get_value)
        text_value = text_button.text
        return text_value
    except NoSuchElementException:
        return None


def get_text_value_by_xpath(web_gui, get_value):
    """To get the text box value using xpath.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element xpath for the text box
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: text box value for required element
    :rtype: string or boolean
    """
    try:
        text_button = web_gui.find_element_by_xpath(get_value)
        text_value = text_button.text
        return text_value
    except NoSuchElementException:
        return None


def get_value_from_disabled_input(web_gui, get_value):
    """To get the value for diabled element.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for required input
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: text value for required element
    :rtype: string
    """
    js = 'return document.getElementById("{!s}").value;'.format(str(get_value))
    text_value = web_gui.execute_script(js)
    return str(text_value)


def get_icon_check_value_by_id(web_gui, get_value):
    """To get the icon button status whether chosen or not using id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for the icon button
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: True if icon button selected else false
    :rtype: boolean
    """
    try:
        icon_button = web_gui.find_elements_by_id(get_value)
        for iconbutton in icon_button:
            icon = iconbutton.get_attribute("src")
            if "icon-check.svg" in icon:
                return True
            else:
                return False
    except NoSuchElementException:
        return None


def get_icon_check_value_by_xpath(web_gui, get_value):
    """To get the icon button status whether chosen or not using xpath.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element xpath for the icon button
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: True if icon button selected else false
    :rtype: boolean
    """
    try:
        icon_button = web_gui.find_elements_by_xpath(get_value)
        for iconbutton in icon_button:
            icon = iconbutton.get_attribute("src")
            if "icon-check.svg" in icon:
                return True
            else:
                return False
    except NoSuchElementException:
        return None


def check_element_is_enable_by_id(web_gui, check_value):
    """To get the enabled text button value using id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param check_value: web element id for the enabled element
    :type check_value: string
    :raises Exception: If error thrown returns None
    :return: enabled text button value
    :rtype: string or boolean
    """
    try:
        text_button = web_gui.find_element_by_id(check_value)
        text_value = text_button.is_enabled()
        return text_value
    except NoSuchElementException:
        return None


def check_active_state_using_class(web_gui, get_value):
    """To check enabled state based on the class value using id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for the enabled element
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: boolean True/False based on state
    :rtype: boolean or None
    """
    try:
        text_button = web_gui.find_element_by_id(get_value)
        text_value = text_button.get_attribute("class")
        if "deactivated" in text_value:
            return False
        else:
            return True
    except NoSuchElementException:
        return None


def get_check_box_value_by_id(web_gui, get_value):
    """To get the check box whether chosen or not using id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for the check box
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: true or false based on check box status
    :rtype: bool
    """
    try:
        box_button = web_gui.find_elements_by_id(get_value)
        for boxbutton in box_button:
            box = boxbutton.get_attribute("src")
            if "check-box-checked.png" in box or "radio-box-checked.png" in box:
                return True
            else:
                return False
    except NoSuchElementException:
        return None


def get_check_box_value_by_xpath(web_gui, get_value):
    """To get the check box whether chosen or not using xpath.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element xpath for the check box
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: true or false based on check box status
    :rtype: boolean
    """
    try:
        box_button = web_gui.find_elements_by_xpath(get_value)
        for boxbutton in box_button:
            box = boxbutton.get_attribute("src")
            if "check-box-checked.png" in box or "radio-box-checked.png" in box:
                return True
            else:
                return False
    except NoSuchElementException:
        return None


def get_element_xpath(web_gui, get_value):
    """To get the UI element with its properties via xpath.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element xpath for the element
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: the web element provided by xpath
    :rtype: object(web element)
    """
    try:
        return web_gui.find_element_by_xpath(get_value)
    except NoSuchElementException:
        return None


def get_element_id(web_gui, get_value):
    """To get the UI element with its properties via id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for the element
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: the web element provided by id
    :rtype: object(web element)
    """
    try:
        return web_gui.find_element_by_id(get_value)
    except NoSuchElementException:
        return None


def get_attribute_element_id(web_gui, get_value, attribute):
    """To get the value of attribute of UI element via id.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element id for the element
    :type get_value: string
    :param attribute: web element value of attribute which is required
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: the value of attribute of web element provided by id
    :rtype: string
    """
    try:
        return web_gui.find_element_by_id(get_value).get_attribute(attribute)
    except NoSuchElementException:
        return None


def get_attribute_element_xpath(web_gui, get_value, attribute):
    """To get the value of attribute of UI element via xpath.

    :param web_gui: web driver after initializing page
    :type web_gui: string
    :param get_value: web element xpath for the element
    :type get_value: string
    :param attribute: web element value of attribute which is required
    :type get_value: string
    :raises Exception: If error thrown returns None
    :return: the value of attribute of web element provided by xpath
    :rtype: string
    """
    try:
        return web_gui.find_element_by_xpath(get_value).get_attribute(
            attribute)
    except NoSuchElementException:
        return None
