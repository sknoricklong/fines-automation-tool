import httpx
import pandas as pd
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
from casescraper import  CaseScraper
import pandas as pd
from io import BytesIO


def longest_streak(data):
    data['date'] = pd.to_datetime(data['date'])
    data.set_index('date', inplace=True)
    fee_table_monthly = data.resample('M').count().reset_index()
    max_streak = 0
    current_streak = 0
    total_paid_months = 0

    # Ensure the values in the data are numeric
    fee_table_monthly = fee_table_monthly.apply(pd.to_numeric, errors='coerce')

    for i, row in fee_table_monthly.iterrows():
        if row[1] > 0:
            total_paid_months += 1
            current_streak += 1

            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0

    return max_streak


def update_amount_by_name(fee_table, first_name, last_name, case_number):
    full_name = f'{last_name.upper()}, {first_name.upper()}'
    name_rows = fee_table[(fee_table['amount'] == 0.0) & (fee_table['description'].str.contains(full_name))]

    for index, row in name_rows.iterrows():
        text = row['description']
        amounts = re.findall(
            r'' + re.escape(case_number) + r':\s*\$([\d,.]+)\s+ON TRANSFER TO.*?' + re.escape(full_name) + r'\b', text)
        if amounts:
            total_amount = sum([float(amount.replace(',', '')) for amount in amounts])
            fee_table.loc[index, 'amount'] = total_amount

    return fee_table

def extract_and_calculate(fee_table, first_name, last_name, case_number):
    fee_table = fee_table.drop_duplicates()
    full_name = f'{last_name.upper()}, {first_name.upper()}'
    if fee_table['party'].isnull().all() or fee_table['party'].eq('').all():
        pass
    else:
        try:
            first_name = first_name.lower()
            last_name = last_name.lower()

            mask = ((fee_table['party'].str.lower().str.contains(first_name)) | \
                    (fee_table['party'].str.lower().str.contains(last_name)) | \
                    (fee_table['description'].str.lower().str.contains(first_name)) & \
                    (fee_table['description'].str.lower().str.contains(last_name))).fillna(False)

            fee_table = fee_table[mask]

        except AttributeError:
            pass

    # Add a new column "payment_plan" with 1 if "payment plan" is found in the 'description' column, 0 otherwise
    has_payment_plan = int(fee_table['description'].str.lower().str.contains('payment plan').any())
    already_received_waiver = int(fee_table['description'].str.lower().str.contains('grants 983a').any())

    # Your original code
    fee_table_issued1 = fee_table[fee_table["amount"].str.contains('\d', na=False)]

    # Fix the SettingWithCopyWarning
    fee_table_issued1 = fee_table_issued1.copy()
    fee_table_issued1.loc[:, 'amount'] = fee_table_issued1['amount'].str.replace('[ ,$]', '', regex=True).astype(float)

    if not (fee_table_issued1['amount'] > 0).any():
        # The alternative code
        fee_table_issued2 = fee_table.copy()
        fee_table_issued2['amount'] = fee_table['description'].str.extract(r'\[(?:.*?)(\d+\.\d{2})(?:.*?)\]')
        fee_table_issued2['amount'] = pd.to_numeric(fee_table_issued2['amount'], errors='coerce')

        fee_table_issued2 = fee_table_issued2[
            ~fee_table_issued2['code'].isin(['ACCOUNT', 'PAY', 'TEXT'])
        ]

        fee_table_issued2 = fee_table_issued2[~fee_table_issued2['code'].str.contains('AC')]

        # Concatenate both results
        fee_table_issued = pd.concat([fee_table_issued1, fee_table_issued2]).drop_duplicates().reset_index(drop=True)
    else:
        fee_table_issued = fee_table_issued1

    total_amount_owed = round(fee_table_issued['amount'].sum(), 2)

    fee_table = fee_table[
        fee_table['code'].isin(['ACCOUNT', 'PAY', 'TEXT'])
    ]

    fee_table_copy = fee_table.copy()

    # Extract the dollar amount from the description column using regular expressions
    pattern = r'TOTAL AMOUNT PAID:\s*\$?\s*(\d+\.\d{2})'
    fee_table['amount'] = fee_table['description'].str.extract(pattern)
    fee_table['amount'] = fee_table['amount'].str.replace('$', '', regex=True).astype(float)
    fee_table = fee_table.dropna(subset=['amount'])
    fee_table = fee_table[fee_table['amount'] >= 0]

    if len(fee_table) == 0:
        pattern = r'TOTAL AMOUNT PAID ON CASE # [A-Za-z0-9-]* : \$\s?(\d+\.\d{2})'
        fee_table = fee_table_copy.copy()
        fee_table['amount'] = fee_table['description'].str.extract(pattern)
        fee_table['amount'] = fee_table['amount'].str.replace('$', '', regex=True).astype(float)
        fee_table = fee_table[fee_table['description'].str.lower().str.contains('receipt', na=False)]

    fee_table.reset_index(drop=True, inplace=True)
    # Update the 'amount' column in fee_table for rows with a 0.0 amount and the full name in the 'description' column
    fee_table = update_amount_by_name(fee_table, first_name, last_name, case_number)
    fee_table_paid = fee_table.copy()
    total_amount_paid = fee_table['amount'].sum()
    fee_table['date'] = pd.to_datetime(fee_table['date'])

    fee_table.set_index('date', inplace=True)
    fee_table_monthly = fee_table.resample('M').count().reset_index()

    def longest_streak(data):
        max_streak = 0
        current_streak = 0
        end_month = None
        total_paid_months = 0

        for i, row in data.iterrows():
            if row[1] > 0:
                total_paid_months += 1
                current_streak += 1

                if current_streak > max_streak:
                    max_streak = current_streak
                    end_month_index = row['date']
                    end_month = fee_table.loc[fee_table.index <= end_month_index].index.max()
                    start_month_index = data.loc[i - max_streak + 1, 'date']
                    start_month = fee_table.loc[fee_table.index >= start_month_index].index.min()
            else:
                current_streak = 0

        return max_streak, total_paid_months, end_month

    streak_length, total_paid_months, streak_end = longest_streak(fee_table_monthly)


    return streak_length, total_paid_months, streak_end, total_amount_paid, total_amount_owed, has_payment_plan, already_received_waiver, fee_table_paid, fee_table_issued

def navigate_and_get_url_soup(url_list, case_list):
    # Set up Chrome options for headless mode
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')

    # Create a new instance of the Chrome driver with headless mode
    service = Service(executable_path=ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    case_soup_dict = {}

    for url, case_number in zip(url_list, case_list):
        # Navigate to the website
        driver.get(url)

        # Wait for the table to load
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))

        # Add an explicit wait to allow more time for the tables to load
        time.sleep(2)

        # Get the page source and parse it with BeautifulSoup
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')

        # Add the case number and soup to the dictionary
        case_soup_dict[case_number] = soup

    # Close the browser window
    driver.quit()

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

@st.cache_data
def load_dataframes():
    alias_df = pd.read_csv("data/alias.csv")
    sentence_df = pd.read_csv("data/sentence.csv", dtype={'id': str, 'prison_sentence': float})
    profile_df = pd.read_csv("data/profile.csv", dtype={'id': str})
    return alias_df, sentence_df, profile_df

@st.cache_data
def filter_alias_df(alias_df, first_name, last_name):
    first_name, last_name = first_name.lower(), last_name.lower()
    filtered_df = alias_df[alias_df['first_name'].str.lower().eq(first_name) & alias_df['last_name'].str.lower().eq(last_name)]
    return filtered_df.astype(str)

@st.cache_data
def filter_sentence_df(sentence_df, id):
    filtered_df = sentence_df.loc[sentence_df['id'].eq(id)].astype(str).copy()
    filtered_df.loc[:, 'crf_number'] = filtered_df['crf_number'].apply(modify_crf_number)
    filtered_df.loc[:, 'community_sentence'] = filtered_df['community_sentence'].astype(float)
    return filtered_df.reset_index(drop=True)

@st.cache_data
def search_profile(profile_df, id):
    official_last_name = None
    official_first_name = None
    official_middle_name = None
    status = None
    facility = None

    filtered_df = profile_df[profile_df['id'].eq(id)]
    if len(filtered_df) > 0:
        status, facility = filtered_df.iloc[0][['status', 'facility']]
        official_last_name = filtered_df['last_name'].values[0]
        official_first_name = filtered_df['first_name'].values[0]
        official_middle_name = filtered_df['middle_name'].values[0] if 'middle_name' in filtered_df.columns else None
    else:
        status, facility = 'ID not found', 'ID not found'
    return status, facility, official_last_name, official_first_name, official_middle_name, filtered_df.reset_index(drop=True)

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


alias_df, sentence_df, profile_df = load_dataframes()

st.title("Step 1: Find Client ID")
st.write("Source: https://okoffender.doc.ok.gov/")

first_name = st.text_input("First name:")
last_name = st.text_input("Last name:")

if first_name and last_name:
    filtered_df = filter_alias_df(alias_df, first_name, last_name)
    st.write(filtered_df.reset_index(drop=True))

st.title("Step 2: Get Offender Record")
st.write("Source: https://okoffender.doc.ok.gov/")
id = st.text_input("Client ID:")

if id:
    filtered_sentence_df = filter_sentence_df(sentence_df, id)

    status, facility, official_last_name, official_first_name, official_middle_name, filtered_profile_df = search_profile(
        profile_df, id)
    st.subheader("Client Information:")
    st.write(filtered_profile_df)

    st.subheader("Sentence Cases:")
    if filtered_sentence_df.empty:
        st.write(f"No sentence information found for {official_first_name} {official_last_name}")
    else:
        filtered_sentence_df = filtered_sentence_df.sort_values(by=['community_sentence'], ascending=False).reset_index(drop=True)
        st.write(filtered_sentence_df)

        eligible_counties = filtered_sentence_df.loc[filtered_sentence_df['community_sentence'].notnull() & (
                    filtered_sentence_df['community_sentence'] > 0), 'sentencing_court'].unique()
        eligible_cases = filtered_sentence_df.loc[filtered_sentence_df['community_sentence'].notnull() & (
                    filtered_sentence_df['community_sentence'] > 0), 'crf_number'].unique()

        st.write(f"Status: {status}")
        st.write(f"Facility: {facility.title()}")

        if eligible_counties.size > 0 and eligible_cases.size > 0:
            st.write(f"Eligible Counties: {', '.join(eligible_counties)}")
            st.write(f"Eligible Cases: {', '.join(eligible_cases)}")
        else:
            st.write("No eligible counties and cases with positive community sentences found.")

def format_county(county):
    county = county.replace(" COUNTY COURT", "")
    return county.title()

st.title("Step 3: Search Cases on ODCR")
st.write("Source: https://www1.odcr.com/")

combined_df = None
selected_courts = []

if first_name and last_name:
    search_checkbox = st.checkbox("Search Cases")
    if search_checkbox:
        party_name = f"{last_name}, {first_name}"
        dataframes = search_cases(party_name)

        if dataframes:
            combined_df = pd.concat(dataframes, axis=0, join='outer', ignore_index=True)
            combined_df = combined_df.sort_values(by=['Court'], ascending=True).reset_index(drop=True)

            unique_courts = combined_df['Court'].unique().tolist()

            try:
                formatted_eligible_counties = [format_county(county) for county in eligible_counties]
                selected_courts = st.multiselect("Select courts:", unique_courts, default=formatted_eligible_counties)
            except:
                selected_courts = st.multiselect("Select courts:", unique_courts, default=unique_courts)


        else:
            st.write("No data found.")
            combined_df = None

if combined_df is not None:
    filtered_df = combined_df.loc[combined_df['Court'].isin(selected_courts)]

    if not filtered_df.empty:
        pass
    else:
        st.write("No data found.")

    if 'filtered_df' in locals():
        filtered_df.insert(0, 'selected', False)
        edited_df = st.experimental_data_editor(filtered_df, use_container_width=True, num_rows="dynamic", key="unique_key")

st.title("Step 4: Select Cases to Find Fees")

if st.button("Done selecting? Click here to pull data."):
    keep_rows = edited_df.loc[edited_df['selected'] == True].index.tolist()
    case_list = edited_df.loc[keep_rows, 'Case Number'].tolist()
    url_list = edited_df.loc[keep_rows, 'Link'].tolist()

    oscn_url_list = [url for url in url_list if "oscn.net" in url]
    oscn_case_list = [case_list[i] for i, url in enumerate(url_list) if "oscn.net" in url]
    non_oscn_url_list = [url for url in url_list if "oscn.net" not in url]
    non_oscn_case_list = [case_list[i] for i, url in enumerate(url_list) if "oscn.net" not in url]

    oscn_case_soup_dict = navigate_and_get_url_soup(oscn_url_list, oscn_case_list)
    oscn_results = process_urls(oscn_case_soup_dict, first_name, last_name)

    non_oscn_results = {}
    for case_number, url in zip(non_oscn_case_list, non_oscn_url_list):
        amount_owed, receipts_table = scrape_odcr(url)
        non_oscn_results[case_number] = (amount_owed, receipts_table)

    results = {**oscn_results, **non_oscn_results}

    total_fees_paid_sum = 0
    total_fees_issued_sum = 0
    total_months_paid_sum = 0

    # Calculate max_consecutive_sum only if oscn_results is not empty
    if oscn_results:
        max_consecutive_sum = max([result[0] for result in oscn_results.values()])
    else:
        max_consecutive_sum = 0

    # Display individual case results
    for case_number, result in results.items():
        st.markdown(f"**Results for Case Number: {case_number}**")
        url_index = case_list.index(case_number)
        if "oscn.net" in url_list[url_index]:
            st.write("URL: ", url_list[url_index])
            streak_length, total_paid_months, streak_end, total_amount_paid, total_amount_owed, has_payment_plan, already_received_waiver, fee_table_paid, fee_table_issued = result
            st.write("Streak Length: ", streak_length)
            st.write("Total Paid Months: ", total_paid_months)
            st.write("Streak End: ", streak_end)
            st.write("Total Amount Paid: ", total_amount_paid)
            st.write("Total Amount Owed: ", total_amount_owed)
            st.write("Fee Table Paid: ", fee_table_paid)
            st.write("Fee Table Issued: ", fee_table_issued)
            total_fees_paid_sum += total_amount_paid
            total_fees_issued_sum += total_amount_owed
            total_months_paid_sum += total_paid_months  # Add this line
        else:
            st.write("URL: ", "https://www1.odcr.com" + url_list[url_index])
            amount_owed, receipts_table = result
            st.write("Amount Owed: ", amount_owed)

            if receipts_table is not None:
                # Convert the "Amount" column to float values
                receipts_table["Amount"] = receipts_table["Amount"].apply(lambda x: float(x.replace('$', '')))
                non_oscn_total_paid = receipts_table[
                    "Amount"].sum()  # Calculate the sum of the amount column if receipts_table is not None
                st.write("Total Amount Paid: ", non_oscn_total_paid)
                total_fees_paid_sum += non_oscn_total_paid
            else:
                non_oscn_total_paid = 0
                st.write("Total Amount Paid: ", non_oscn_total_paid)
            st.write("Receipts Table: ", receipts_table)

            total_fees_issued_sum += amount_owed
        st.write("---")

    st.title("Summary:")
    st.write("Total Cases Searched: ", len(results))
    st.write("Total Fees Issued: ", total_fees_issued_sum)
    st.write("Total Fees Paid: ", total_fees_paid_sum)
    st.write("Total Months Paid: ", total_months_paid_sum)
    st.write("Max Consecutive Months Paid: ", max_consecutive_sum)


    def generate_excel_content(results, summary):
        output = BytesIO()

        # Create a summary DataFrame
        summary_df = pd.DataFrame(
            data=summary,
            index=[0],
            columns=['Total Cases Searched', 'Total Fees Issued', 'Total Fees Paid', 'Total Months Paid',
                     'Max Consecutive Months Paid - Individual']
        )

        # Initialize DataFrames for combined fee_table_paid and individual case summaries
        combined_fee_table_paid = pd.DataFrame()
        individual_case_summaries = pd.DataFrame()

        # Save individual case information to separate sheets and update combined_fee_table_paid
        for case_number, result in results.items():
            url_index = case_list.index(case_number)
            url = url_list[url_index]
            if "oscn.net" in url:
                streak_length, total_paid_months, _, total_amount_paid, total_amount_owed, _, _, fee_table_paid, fee_table_issued = result
                receipts_table = None
            else:
                url = "https://www1.odcr.com" + url
                total_amount_owed, receipts_table = result
                total_amount_paid = sum(receipts_table["Amount"]) if receipts_table is not None else 0
                fee_table_paid = fee_table_issued = None
                streak_length = total_paid_months = None

            # Create a DataFrame with the individual case information (topline)
            case_info_df = pd.DataFrame(
                data={
                    'Case Number': [case_number],
                    'URL': [url],
                    'Total Amount Owed': [total_amount_owed],
                    'Total Amount Paid': [total_amount_paid],
                    'Streak Length': [streak_length],
                    'Total Paid Months': [total_paid_months]
                }
            )

            # Append individual case summary to the DataFrame
            individual_case_summaries = individual_case_summaries.append(case_info_df, ignore_index=True)

            # Append fee_table_paid to the combined DataFrame
            if fee_table_paid is not None:
                combined_fee_table_paid = combined_fee_table_paid.append(fee_table_paid, ignore_index=True)

        # Calculate the longest streak for the combined fee_table_paid
        max_combined_streak = longest_streak(combined_fee_table_paid.reset_index())
        summary_df['Max Consecutive Months Paid - All'] = max_combined_streak

        # Save summary DataFrame, individual_case_summaries, and combined_fee_table_paid to the first sheet
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            individual_case_summaries.to_excel(writer, sheet_name='Summary', index=False, startrow=len(summary_df) + 1)

            combined_fee_table_paid['date'] = pd.to_datetime(combined_fee_table_paid['date'])
            combined_fee_table_paid = combined_fee_table_paid.sort_values(by='date')
            combined_fee_table_paid['date'] = combined_fee_table_paid['date'].dt.strftime('%m-%d-%Y')
            combined_fee_table_paid.reset_index(drop=True, inplace=True)
            combined_fee_table_paid.to_excel(writer, sheet_name='Summary', index=True,
                                             startrow=len(summary_df) + len(individual_case_summaries) + 3)

            # Save individual case information to separate sheets
            for case_number, result in results.items():
                url_index = case_list.index(case_number)
                url = url_list[url_index]
                if "oscn.net" in url:
                    streak_length, total_paid_months, _, total_amount_paid, total_amount_owed, _, _, fee_table_paid, fee_table_issued = result
                    receipts_table = None
                else:
                    url = "https://www1.odcr.com" + url
                    total_amount_owed, receipts_table = result
                    total_amount_paid = sum(receipts_table["Amount"]) if receipts_table is not None else 0
                    fee_table_paid = fee_table_issued = None
                    streak_length = total_paid_months = None

                    # Create a DataFrame with the individual case information (topline)
                case_info_df = pd.DataFrame(
                    data={
                        'Case Number': [case_number],
                        'URL': [url],
                        'Total Amount Owed': [total_amount_owed],
                        'Total Amount Paid': [total_amount_paid],
                        'Streak Length': [streak_length],
                        'Total Paid Months': [total_paid_months]
                    }
                )

                # Save the individual case information to a new sheet
                case_info_df.to_excel(writer, sheet_name=f'Case {case_number}', index=False, startrow=0)

                # Save fee_table_paid, fee_table_issued, and receipts_table to the same sheet
                workbook = writer.book
                worksheet = writer.sheets[f'Case {case_number}']

                if fee_table_paid is not None:
                    fee_table_paid.to_excel(writer, sheet_name=f'Case {case_number}', index=False, startrow=5)
                    worksheet.write(4, 0, 'Fee Table Paid')
                if fee_table_issued is not None:
                    fee_table_issued.to_excel(writer, sheet_name=f'Case {case_number}', index=False, startrow=5,
                                              startcol=fee_table_paid.shape[1] + 1)
                    worksheet.write(4, fee_table_paid.shape[1] + 1, 'Fee Table Issued')
                if receipts_table is not None:
                    startcol = fee_table_paid.shape[1] + fee_table_issued.shape[1] + 2
                    receipts_table.to_excel(writer, sheet_name=f'Case {case_number}', index=False, startrow=5,
                                            startcol=startcol)
                    worksheet.write(4, startcol, 'Receipts Table')

            output.seek(0)
            return output

    excel_content = generate_excel_content(results, {
        'Total Cases Searched': len(results),
        'Total Fees Issued': total_fees_issued_sum,
        'Total Fees Paid': total_fees_paid_sum,
        'Total Months Paid': total_months_paid_sum,
        'Max Consecutive Months Paid - Individual': max_consecutive_sum
    })

    st.download_button(
        label="Download Excel",
        data=excel_content,
        file_name=f"{last_name}_{first_name}_.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


