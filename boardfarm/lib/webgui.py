import os
import time
import traceback
from pyvirtualdisplay import Display

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

from gui_helper import click_button_id, enter_input, get_radio_button_value, get_text_value, get_drop_down_value, select_option_by_id
from common import resolv_dict, get_webproxy_driver

class web_gui():
    prefix = ''
    def __init__(self,
                 output_dir=os.path.join(os.getcwd(), "results"),
                 **kwargs):
        self.output_dir = output_dir
        self.default_delay = 30
        self.driver = None
        self.display = None

    # this specified a prefix for the screenshots file names
    # it cna be used to prepend the testcase name to the file name
    def set_prefix(self, prefix=''):
        self.prefix = prefix

    def _save_screenshot(self, name):
        full_path = os.path.join(self.output_dir, name)
        self.driver.save_screenshot(full_path)
        return full_path

    def enter_input_value(self, key_id, input_value):
        key_value = self.key[key_id]
        select_value = resolv_dict(self.config, key_value)
        self.scroll_view(select_value)
        enter_value = enter_input(self.driver, select_value, input_value)
        assert enter_value, 'Unable to enter value %s' % input_value

    def get_text(self, value):
        key_value = self.key[value]
        key_value = eval("self.config"+key_value)
        text = get_text_value(self.driver, key_value)
        return text

    def click_button(self, key_id):
        select_id = self.key[key_id]
        select_key_value = resolv_dict(self.config, select_id)
        self.scroll_view(select_key_value)
        Click_button = click_button_id(self.driver, select_key_value)
        assert Click_button == True, 'Click button : %s  ' % Click_button

    def selected_option_by_id(self, key_id, value):
        select_id = self.key[key_id]
        select_key_value = resolv_dict(self.config, select_id)
        self.scroll_view(select_key_value)
        select_button = select_option_by_id(self.driver, select_key_value,value)
        assert select_button , 'Select button : %s  ' % select_button

    def verify_radio(self, value):
        key_value = self.key[value]
        key_value = resolv_dict(self.config, key_value)
        key_value = get_radio_button_value(self.driver, key_value)
        assert key_value, 'Changes are not applied properly'

    def verify_drop_down(self, value, check_value):
        key_value = self.key[value]
        key_value = resolv_dict(self.config, key_value)
        keyvalue = get_drop_down_value(self.driver, key_value)
        if keyvalue == check_value:
            return True
        else:
            return False

    def verify_text(self, value, text):
        key_value = self.key[value]
        key_value = resolv_dict(self.config, key_value)
        key_value = get_text_value(self.driver, key_value)
        if key_value == text:
            return True
        else:
            return False

    def scroll_view(self, scroll_value):
        # Scrolling into the particular option for better view
        self.driver.execute_script("arguments[0].scrollIntoView();", self.driver.find_element_by_id(scroll_value))

    def _enter_text(self, txt_box, txt):
        txt_list = list(txt)
        for c in txt_list:
            time.sleep(0.1)
            txt_box.send_keys(c)

    def check_element_visibility(self, *element, **kwargs):
        '''ex. *element=('id, 'element') or ('name, 'element')'''
        timeout = kwargs.get('timeout', self.default_delay)
        query = None
        try:
            query = WebDriverWait(self.driver, timeout).until(
                    EC.visibility_of_element_located(element))
        except:
            print('check_element_visibility(%s, %s): timeout to find element\n' % element)
        finally:
            return query

    def check_element_clickable(self, *element, **kwargs):
        timeout = kwargs.get('timeout', self.default_delay)
        query = None
        try:
            query = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable(element))
        except:
            print('check_element_clickable(%s, %s): timeout to find element\n' % element)
        finally:
            return query

    def check_element_selection_state_to_be(self, *element, **kwargs):
        timeout = kwargs.get('timeout', self.default_delay)
        query = None
        try:
            query = WebDriverWait(self.driver, timeout).until(
                    EC.element_selection_state_to_be(element))
        except:
            print('check_element_selection_state_to_be(%s, %s): timeout to find element\n' % element)
        finally:
            return query

    def wait_for_element(self, index_by='id', ele_index=None):
        '''wait for element exist'''
        assert ele_index != None, 'ele_index=None'
        if index_by == 'name':
            by = By.NAME
        else:
            by = By.ID

        self.driver.implicitly_wait(self.default_delay)

        print('wait_for_element(): check_element_visibility(%s, %s)' % (str(by), ele_index))
        ele = self.check_element_visibility(by, ele_index)
        assert ele != None, 'check_element_visibility(%s, %s)=False' % (str(by), ele_index)

    def check_element_exists(self, text):
        try:
            element = self.driver.find_element_by_xpath(text)
            print("Element '" + text + "' found")
            return element
        except NoSuchElementException:
            print("check_element_exists No element '" + text + "' found")
            return None

    def check_element_exists_by_name(self, text):
        try:
            element = self.driver.find_element_by_name(text)
            print("Element '" + text + "' found")
            return element
        except NoSuchElementException:
            print("No element '" + text + "' found")
            return None

    def wait_for_redirects(self):
        # wait for possible redirects to settle down
        url = self.driver.current_url
        for i in range(10):
            time.sleep(5)
            if url == self.driver.current_url:
                break
            url = self.driver.current_url

    def gui_logout(self, id_value):
        try:
            ele_botton = self.check_element_clickable(By.ID, id_value, timeout=3)
            if ele_botton != None:
                ele_botton.click()
                print("Logout clicked")
            return True
        except NoSuchElementException:
            print("No logout botton element ('id', %s) found " % id_value)
            return False

    def driver_close(self, logout_id):
        self.gui_logout(logout_id)
        self.driver.quit()
        print('driver quit')
        if self.display != None:
            self.display.stop()
            print('display stop')

    # Starts the python wrapper for Xvfb, Xephyr and Xvnc
    # the backend can be set via BFT_OPTIONS
    def open_display(self):
        from boardfarm import config
        xc, yc = config.default_display_backend_size.split('x')
        x = int(xc)
        y = int(yc)
        self.display = Display(backend=config.default_display_backend,
                               rfbport=config.default_display_backend_port,
                               rfbauth=os.environ['HOME'] + '/.vnc/passwd',
                               visible=0,
                               size=(x, y))
        self.display.start()

    def get_web_driver(self, proxy):
        from boardfarm import config
        try:
            self.driver = get_webproxy_driver(proxy, config)
        except:
            traceback.print_exc()
            raise Exception("Failed to get webproxy driver via proxy " + proxy)
        return self.driver

    def botton_click_to_next_page(self, index_by='id', ele_index=None):
        '''click botton and verify'''
        assert ele_index != None, 'ele_index=None'
        if index_by == 'name':
            by = By.NAME
        else:
            by = By.ID

        # verify $botton is exist
        botton = self.check_element_visibility(by, ele_index)
        assert botton != None, 'timeout: not found %s in page' % ele_index
        print('get botton value: %s' % botton.get_attribute("value"))

        # check_element_clickable() and click()
        self._save_screenshot('%s_click.png' % ele_index)
        self.check_element_clickable(by, ele_index).click()

    def home_page(self, page_id):
        home_page = self.check_element_visibility(By.ID, page_id)
        # wait for possible redirects to settle down
        self.wait_for_redirects()
        time.sleep(10)
        assert home_page != None, 'timeout: not found home page'
        print(home_page.text)
        self._save_screenshot(self.prefix + 'home_page.png')

    def navigate_to_target_page(self, navi_path):
        '''using this for navigation'''
        for path in navi_path:
            temp = self.key[path]
            temp = resolv_dict(self.config, temp)
            button = click_button_id(self.driver, temp)
            assert button, 'Error in click %s' % path
            print("Click %s : PASS" % path)
            time.sleep(2)
