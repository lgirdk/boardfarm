# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import json
import os
import config
from lib.common import *

from selenium import webdriver
from selenium.webdriver.common.proxy import *
from pyvirtualdisplay import Display
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.select import Select
from time import sleep

def enter_input(web_gui, input_path, input_value):
    #enter input value in text box for web page
    input_tab = web_gui.find_element_by_id(input_path)
    assert input_tab != None, 'timeout: page not found'
    input_tab.clear()
    input_tab.send_keys(input_value)

def click_button_id(web_gui, clickbutton):
    #to click any button using id
    click_tab = web_gui.find_element_by_id(clickbutton)
    assert click_tab != None, 'timeout: page not found'
    click_tab.click()
    time.sleep(10)

def click_button_xpath(web_gui, clickbutton):
    #to click any button using xpath
    click_tab = web_gui.find_element_by_xpath(clickbutton)
    assert click_tab != None, 'timeout: page not found'
    click_tab.click()
    time.sleep(5)

def select_option(web_gui, select_button, select_value):
    #To select the option required
    select = Select(web_gui.find_element_by_id(select_button))
    assert select != None, 'timeout: not found option to select '
    select.select_by_visible_text(select_value)
    time.sleep(5)

def get_drop_down_value(web_gui, get_value):
    #To get the value which already exists
    select = Select(web_gui.find_element_by_id(get_value))
    assert select != None, 'timeout: data not found'
    selected_option = select.first_selected_option
    selected_value = selected_option.text
    return selected_value

def get_radio_button_value(web_gui, get_value):
    radio_button = web_gui.find_elements_by_id(get_value)
    assert radio_button != None, 'timeout: data not found'
    for radiobutton in radio_button:
        radio = radiobutton.get_attribute('src')
        if "radio-box-checked" in radio:
            return True
        else:
            return False

def get_text_value(web_gui, get_value):
    text_button = web_gui.find_element_by_id(get_value)
    assert text_button != None, 'timeout: data not found'
    text_value = text_button.text
    return text_value
