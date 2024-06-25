# coding: utf-8
'''
------------------------------------------------------------------------------
Copyright 2024 Kate Ward
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
 http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
------------------------------------------------------------------------------
'''
from selenium import webdriver
from time import sleep
import json
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from prometheus_client import Gauge, start_http_server
from os import path

def html_to_json(content, indent=None):
    soup = BeautifulSoup(content, "html.parser")
    rows = soup.find_all("tr")
    
    headers = {}
    thead = soup.find("thead")
    if thead:
        thead = soup.find_all("th")
        for i in range(len(thead)):
            headers[i] = thead[i].text.strip().lower()
    data = []
    for row in rows:
        cells = row.find_all("td")
        if thead:
            items = {}
            if len(cells) > 0:
                for index in headers:
                    items[headers[index]] = cells[index].text
        else:
            items = []
            for index in cells:
                items.append(index.text.strip())
        if items:
            data.append(items)
    return json.dumps(data, indent=indent)

config_default = {
    'time_between_restart': 15.0,
    'requests_per_instance': 10,
    'time_between_request': 5.0,
    'sleep_after_login': 4.5,
    'sleep_after_networkpage_load': 2.0,
    
    'router_base_url': 'http://192.168.0.1',
    'router_username': 'admin',
    'router_password': 'Telstra',
    
    'prometheus_port': 8080
}
config = config_default
if path.exists('config.json'):
    with open('config.json', 'r') as f:
        data = json.loads(f)
        for k in data.keys():
            config[k] = data[k]
            print('set %s=%s' % (k, data[k]))
    print('loaded config!')
else:
    print('no config.json found, using defaults :3')

# initialize the driver and return it
def init_driver():
    options = webdriver.FirefoxOptions()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options)
    print('navigating to login page')
    driver.get('%s/login.htm' % config['router_base_url'])
    print('at login page')
    login_username_textbox = driver.find_element(by=By.ID, value="usernameNormal")
    login_username_textbox.clear()
    login_username_textbox.send_keys(config['router_username'])
    print('entered username text')
    login_password_textbox = driver.find_element(by=By.ID, value="passwordNormal")
    login_password_textbox.clear()
    login_password_textbox.send_keys(config['router_password'])
    print('entered password text')
    login_login_button = driver.find_element(by=By.CSS_SELECTOR, value='img[alt="sign in"]')
    login_login_button.click()
    print('clicked on the login button')
    sleep(config['sleep_after_login'])
    if driver.current_url is not ('%s/home.htm' % config['router_base_url']):
        print('current url isn\'t the home! it\'s %s' % driver.current_url)
        exit(1)
    return driver
# fetch diagnostics data from /diagnostics_network.htm
# specifically the table with the id of `networkstats` will be turned into json
# and returned.
def fetch_diagnostics_data(driver):
    print('navigating to network diagnostics page')
    driver.get('%s/diagnostics_network.htm?m=adv' % config['router_base_url'])
    sleep(config['sleep_after_networkpage_load'])
    diagnostics_table = driver.find_element(by=By.ID, value="networkstats")
    diagnostics_raw = diagnostics_table.get_attribute('innerHTML')
    diagnostics_raw = '<table>%s</table>' % diagnostics_raw
    diagnostics_data = html_to_json(diagnostics_raw, indent='    ')
    print('generated diagnostics data :3')
    return diagnostics_data

c_b_r = Gauge('bytes_rx', 'Bytes received', labelnames=['interface', 'interface_state'])
c_b_t = Gauge('bytes_tx', 'Bytes sent', labelnames=['interface', 'interface_state'])
c_p_r = Gauge('packets_rx', 'Packets received', labelnames=['interface', 'interface_state'])
c_p_t = Gauge('packets_tx', 'Packets sent', labelnames=['interface', 'interface_state'])
c_e_r = Gauge('errors_rx', 'Received errors', labelnames=['interface', 'interface_state'])
c_e_t = Gauge('errors_tx', 'Sent errors', labelnames=['interface', 'interface_state'])

# set gauges to the stuff from `fetch_diagnostics_data`
def set_diag_gauges(data):
    for x in data:
        i_cbr = c_b_r.labels(x['interface'], x['state'])
        i_cbr._value._value = int(0)
        i_cbr.set(int(x['rx bytes']))
        
        i_cbt = c_b_t.labels(x['interface'], x['state'])
        i_cbt._value._value = int(0)
        i_cbt.set(int(x['tx bytes']))
        
        i_cpr = c_p_r.labels(x['interface'], x['state'])
        i_cpr._value._value = int(0)
        i_cpr.set(int(x['rx packets']))
        
        i_cpt = c_p_t.labels(x['interface'], x['state'])
        i_cpt._value._value = int(0)
        i_cpt.set(int(x['tx packets']))
        
        i_cer = c_e_r.labels(x['interface'], x['state'])
        i_cer._value._value = int(0)
        i_cer.set(int(x['rx errors']))
        
        i_cet = c_e_t.labels(x['interface'], x['state'])
        i_cet._value._value = int(0)
        i_cet.set(int(x['tx errors']))


start_http_server(config['prometheus_port'])
def logic():
    driver = init_driver()
    request_count = 0
    request_count_max = config['requests_per_instance']
    time_between_request = config['time_between_request']
    while request_count < request_count_max:
        data = fetch_diagnostics_data(driver)
        set_diag_gauges(json.loads(data))
        request_count += 1
        print('waiting %ss' % time_between_request)
        sleep(time_between_request)
    driver.quit()
while True:
    logic()
    sleep(config['time_between_restart'])
    print('======== restarting loop')