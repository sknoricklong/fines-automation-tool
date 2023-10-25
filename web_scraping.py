import re
import requests
import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import httpx
import pandas as pd


def navigate_and_get_url_soup(url_list, case_list, guid):
    headers = {
        "User-Agent": guid,  # using GUID as the User-Agent
    }

    case_soup_dict = {}

    with httpx.Client() as client:
        for url, case_number in zip(url_list, case_list):
            # Navigate to the website
            response = client.get(url, headers=headers)
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

def extract_fee_table(soup):
    tables = soup.select("table[id*='results-list']")  # Select tables with 'results-list' in the id
    dataframes = []
    for table in tables:
        try:
            df = pd.read_html(str(table))[0]

            # Extract links from the table
            rows = table.find_all('tr')
            links = []
            for row in rows[1:]:  # Skip the header row
                link_cell = row.find('a', href=True)
                if link_cell:
                    links.append(link_cell['href'])
                else:
                    links.append(None)

            # Add a new column to the DataFrame with the links
            df['Link'] = links

            dataframes.append(df)
        except:
            pass
    return dataframes


def extract_docket_table(soup):
    tables = soup.select("table.docketlist.ocis, table.docketlist.kp")
    dataframes = []
    for table in tables:
        try:
            df = pd.read_html(str(table))[0]
            dataframes.append(df)
        except:
            pass
    fee_table = pd.concat(dataframes)
    fee_table.columns = [col.lower() for col in fee_table.columns]
    fee_table['date'] = fee_table['date'].fillna(method='ffill')
    default_amount = ""
    fee_table['amount'].fillna(default_amount, inplace=True)

    return fee_table


@st.cache_data
def search_cases(party_name):
    url = "https://www1.odcr.com/"

    # Set up Chrome options for headless mode
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')

    # Create a new instance of the Chrome driver with headless mode
    service = Service(executable_path=ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Navigate to the website
    driver.get(url)

    # Find the input field by id and send the party_name
    input_element = driver.find_element(By.ID, "search-party")
    input_element.send_keys(party_name)

    # Click the "Search for cases" button
    submit_button = driver.find_element(By.XPATH, '//input[@type="submit"]')
    submit_button.click()

    # Wait for the table to load
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))

    # Add an explicit wait to allow more time for the tables to load
    time.sleep(2)

    # Get the page source and parse it with BeautifulSoup
    html_content = driver.page_source
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract the DataFrames using BeautifulSoup
    dataframes = extract_fee_table(soup)

    # Close the browser window
    driver.quit()

    return dataframes



def modify_crf_number(value):
    num_parts = value.split('-')
    if len(num_parts[0]) == 2:
        num = int(num_parts[0])
        num_parts[0] = '19' + num_parts[0] if num >= 24 else '20' + num_parts[0]
    return '-'.join(num_parts)


def scrape_odcr(url):
    # Add the desired URL prefix to the URL if it doesn't have one already
    if not url.startswith('http'):
        url = "https://www1.odcr.com/" + url

    # Send a GET request to the website and get the page content
    response = requests.get(url)
    html_content = response.content

    # Parse the HTML content with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract the amount owed from the table
    amount_owed = None
    th_elements = soup.find_all('th', text="Amount Owed")
    if th_elements:
        td_element = th_elements[0].find_next('td')
        amount_owed_str = td_element.text.strip().split()[0]
        amount_owed = float(amount_owed_str.replace('$', ''))

    # Extract the table under the section id named "receipts"
    receipts_table = None
    receipts_section = soup.find('section', {'id': 'receipts'})
    if receipts_section:
        receipts_table = pd.read_html(str(receipts_section))[0].iloc[:-1]

    return amount_owed, receipts_table