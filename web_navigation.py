from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import httpx
from data_processing import *




def navigate_and_get_url_soup(url_list, case_list, guid):
    headers = {
        "User-Agent": guid,  # using GUID as the User-Agent
    }

    case_soup_dict = {}

    for url, case_number in zip(url_list, case_list):
        # Navigate to the website
        headers = {
            "User-Agent": guid,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        # Make the request
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Ensure we've got a successful response

        # Parse the response with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Add the case number and soup to the dictionary
        case_soup_dict[case_number] = soup
        time.sleep(1)

    return case_soup_dict

def process_urls(case_soup_dict, first_name, last_name):
    results = {}

    for case_number, soup in case_soup_dict.items():
        fee_table = extract_docket_table(soup)
        result = extract_and_calculate(fee_table, first_name, last_name, case_number)
        results[case_number] = result

    return results