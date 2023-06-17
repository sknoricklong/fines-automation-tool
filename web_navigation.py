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
    url_list, case_list = zip(*set(zip(url_list, case_list)))

    case_soup_dict = {}
    total_cases = len(case_list)  # Get total cases to be processed

    headers = {
        "User-Agent": guid,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }

    url = url_list[0]

    # Make the request
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    st.write(soup)

    # # Reserve a slot
    # progress_text = st.empty()
    #
    # for i, (url, case_number) in enumerate(zip(url_list, case_list), start=1):
    #     # Navigate to the website
    #     headers = {
    #         "User-Agent": guid,
    #         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    #     }
    #
    #     # Make the request
    #     response = requests.get(url, headers=headers)
    #     response.raise_for_status()  # Ensure we've got a successful response
    #
    #     # Parse the response with BeautifulSoup
    #     soup = BeautifulSoup(response.text, 'html.parser')
    #
    #     # Add the case number and soup to the dictionary
    #     case_soup_dict[case_number] = soup
    #
    #     # Update the message in the reserved slot
    #     progress_text.text(f'Finished {i} of {total_cases}: {case_number}')
    #
    #     time.sleep(1)
    #
    # return case_soup_dict
def process_urls(case_soup_dict, first_name, last_name):
    results = {}

    for case_number, soup in case_soup_dict.items():
        fee_table = extract_docket_table(soup)
        result = extract_and_calculate(fee_table, first_name, last_name, case_number)
        results[case_number] = result

    return results