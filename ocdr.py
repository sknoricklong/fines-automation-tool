import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import requests

def extract_fee_table(soup):
    tables = soup.select("table[id*='results-list']")  # Select tables with 'results-list' in the id
    dataframes = []
    for table in tables:
        try:
            df = pd.read_html(str(table))[0]
            dataframes.append(df)
        except:
            pass
    return dataframes

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
    time.sleep(5)

    # Get the page source and parse it with BeautifulSoup
    html_content = driver.page_source
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract the DataFrames using BeautifulSoup
    dataframes = extract_fee_table(soup)

    # Close the browser window
    driver.quit()

    return dataframes



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


url = "detail?court=050-&casekey=050-TR++9901592"
print(scrape_odcr(url))
