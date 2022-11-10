import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
import ddddocr
import time
import logging
import traceback
import subprocess
import re
from const import *


class DataFetcher:

    def __init__(self, username: str, password: str):

        self._username = username
        self._password = password
        self._ocr = ddddocr.DdddOcr(show_ad = False)
        self._chromium_version = self._get_chromium_version()

    
    def fetch(self):
        for retry_times in range(1, RETRY_TIMES_LIMIT + 1):
            try:
                return self._fetch()
            except Exception as e:
                if(retry_times == RETRY_TIMES_LIMIT):
                    raise e
                traceback.print_exc()
                logging.error(f"Webdriver quit abnormly, reason: {e}. {RETRY_TIMES_LIMIT - retry_times} retry times left.")
                wait_time = retry_times * RETRY_WAIT_TIME_OFFSET_UNIT
                time.sleep(wait_time)
                
            
    
    def _fetch(self):
        driver = self._get_webdriver()
        logging.info("Webdriver initialized.")
        try:
            self._login(driver)
            logging.info(f"Login successfully on {LOGIN_URL}" )
            user_id_list = self._get_user_ids(driver)
            balance_list = self._get_electric_balances(driver, user_id_list)
            last_daily_usage_list, yearly_charge_list, yearly_usage_list = self._get_other_data(driver, user_id_list)       
            driver.quit()
            logging.debug("Webdriver quit after fetching data successfully.")

            return user_id_list, balance_list, last_daily_usage_list, yearly_charge_list, yearly_usage_list

        finally:
                driver.quit()  

    def _get_webdriver(self):
        chrome_options = Options()
        chrome_options.add_argument('--incognito')
        chrome_options.add_argument('--window-size=4000,1600')
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-dev-shm-usage') 
        driver = uc.Chrome(driver_executable_path = "/usr/bin/chromedriver" ,options = chrome_options, version_main = self._chromium_version)
        driver.implicitly_wait(DRIVER_IMPLICITY_WAIT_TIME)
        return driver

    def _login(self, driver):
        driver.get(LOGIN_URL)
        driver.find_element(By.CLASS_NAME,"user").click()
        input_elements = driver.find_elements(By.CLASS_NAME,"el-input__inner")
        input_elements[0].send_keys(self._username)
        input_elements[1].send_keys(self._password)
        
        
        captcha_element = driver.find_element(By.CLASS_NAME,"code-mask")
        
        for retry_times in range(1, RETRY_TIMES_LIMIT + 1):

            img_src = captcha_element.find_element(By.TAG_NAME,"img").get_attribute("src")
            img_base64 = img_src.replace("data:image/jpg;base64,","")
            orc_result = str(self._ocr.classification(ddddocr.base64_to_image(img_base64)))

            if(not self._is_captcha_legal(orc_result)):
                logging.debug(f"The captcha is illegal, which is caused by ddddocr, {RETRY_TIMES_LIMIT - retry_times} retry times left.")
                WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(captcha_element))
                driver.execute_script("arguments[0].click();", captcha_element)
                time.sleep(2)
                continue

            input_elements[2].send_keys(orc_result)

            login_button = driver.find_element(By.CLASS_NAME, "el-button.el-button--primary")
            WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(login_button))
            driver.execute_script("arguments[0].click();", login_button)
            try:
                return WebDriverWait(driver,LOGIN_EXPECTED_TIME).until(EC.url_changes(LOGIN_URL))
            except:
                logging.debug(f"Login failed, maybe caused by invalid captcha, {RETRY_TIMES_LIMIT - retry_times} retry times left.")

        raise Exception("Login failed, please check your phone number and password!!!")

    def _get_electric_balances(self, driver, user_id_list):
        balance_list = []
        driver.get(BALANCE_URL)
        for i in range(1, len(user_id_list) + 1):
            balance = self._get_eletric_balance(driver)
            logging.info(f"Get electricity charge balance for {user_id_list[i-1]} successfully, balance is {balance} CNY.")
            balance_list.append(balance)

            if(i != len(user_id_list)):
                roll_down_button = driver.find_element(By.CLASS_NAME, "el-input__inner")
                WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(roll_down_button))
                roll_down_button.click()
                next_one = driver.find_element(By.XPATH, f"//ul[@class='el-scrollbar__view el-select-dropdown__list']/li[{i + 1}]")
                WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(next_one))
                next_one.click()
        return balance_list
    
    def _get_other_data(self, driver, user_id_list):
        last_daily_usage_list =[]
        yearly_usage_list = []
        yearly_charge_list = []
        driver.get(ELECTRIC_USAGE_URL)
        for i in range(1, len(user_id_list) + 1):

            yearly_usage, yearly_charge = self._get_yearly_data(driver)
            logging.info(f"Get year power consumption for {user_id_list[i-1]} successfully, usage is {yearly_usage} kwh, yealrly charge is {yearly_charge} CNY")

            last_daily_usage = self._get_yesterday_usage(driver)
            logging.info(f"Get daily power consumption for {user_id_list[i-1]} successfully, usage is {last_daily_usage} kwh.")

            last_daily_usage_list.append(last_daily_usage)
            yearly_charge_list.append(yearly_charge)
            yearly_usage_list.append(yearly_usage)

            if(i != len(user_id_list)):
                click_element = driver.find_element(By.CLASS_NAME, "el-input.el-input--suffix")
                WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(click_element))
                driver.execute_script("arguments[0].click();", click_element)
                click_element2 =  driver.find_element(By.XPATH, f"//body/div[@class='el-select-dropdown el-popper']//ul[@class='el-scrollbar__view el-select-dropdown__list']/li[{i + 1}]")
                WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(click_element2))
                driver.execute_script("arguments[0].click();", click_element2)
            
        return last_daily_usage_list, yearly_charge_list, yearly_usage_list

    @staticmethod
    def _get_user_ids(driver):
        roll_down_button = driver.find_element(By.XPATH, "//div[@class='el-dropdown']/span")
        WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(roll_down_button))
        driver.execute_script("arguments[0].click();", roll_down_button)
        target = driver.find_element(By.CLASS_NAME, "el-dropdown-menu.el-popper").find_element(By.TAG_NAME, "li")
        WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(target))
        userid_elements = driver.find_element(By.CLASS_NAME, "el-dropdown-menu.el-popper").find_elements(By.TAG_NAME, "li")
        userid_list = []
        for element in userid_elements:
            userid_list.append(re.findall("[0-9]+", element.text)[-1])
        return userid_list

    def _get_eletric_balance(self, driver):
        balance = driver.find_element(By.CLASS_NAME,"num").text
        return float(balance)
    
    def _get_yearly_data(self, driver):
        click_element = driver.find_element(By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-first']")
        WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(click_element))
        driver.execute_script("arguments[0].click();", click_element)
        target = driver.find_element(By.CLASS_NAME, "total")
        
        WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(target))
        yearly_usage = driver.find_element(By.XPATH, "//ul[@class='total']/li[1]/span").text
        yearly_charge = driver.find_element(By.XPATH, "//ul[@class='total']/li[2]/span").text
        return yearly_usage, yearly_charge

        

    def _get_yesterday_usage(self, driver):
        click_element = driver.find_element(By.XPATH,"//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
        WebDriverWait(driver, DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(click_element))
        driver.execute_script("arguments[0].click();", click_element)
        usage = driver.find_element(By.XPATH,"//div[@class='el-table__body-wrapper is-scrolling-none']//td[2]/div").text
        return(float(usage))

    @staticmethod
    def _is_captcha_legal(captcha):
        if(len(captcha) != 4): 
            return False
        for s in captcha:
            if(not s.isalpha() and not s.isdigit()):
                return False
        return True
    
    @staticmethod
    def _get_chromium_version():
        result = str(subprocess.check_output(["chromium", "--product-version"]))
        return re.findall(r"(\d*)\.",result)[0]

if(__name__ == "__main__"):
    fetcher = DataFetcher("18622517008","Lzr519812")
    print(fetcher.fetch())
