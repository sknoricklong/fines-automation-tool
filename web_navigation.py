from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import httpx
from data_processing import *
from bs4 import BeautifulSoup as bs



def process_urls(case_soup_dict, first_name, last_name):
    results = {}

    for case_number, soup in case_soup_dict.items():
        fee_table = extract_docket_table(soup)
        result = extract_and_calculate(fee_table, first_name, last_name, case_number)
        results[case_number] = result

    return results