from oscndocketscraper import OSCNDocketScraper
from oscncasescraper import OSCNCaseScraper

import streamlit as st
import pandas as pd
import pickle
import time

from casescraper import CaseScraper

# testing
# Calculate total fees paid
def calculate_total_fees(df):
    # calculate total fees paid
    total_fees = df['amount'].sum()
    return total_fees

# Calculate number of consecutive months paid
def calculate_consecutive_months(df):
    # convert the 'date' column to a pandas datetime object
    df['date'] = pd.to_datetime(df['date'])

    # generate a list of consecutive months
    month_list = []
    for i in range(len(df)-1):
        current_month = df['date'][i].month
        next_month = df['date'][i+1].month
        if (next_month - current_month) == 1:
            month_list.append(current_month)
        else:
            month_list.append(current_month)
            month_list.append('break')

    # loop through the month list to find the longest consecutive sequence
    max_consecutive = 0
    consecutive_count = 0
    total_months_paid = 0
    start_index = 0
    end_index = 0
    temp_start_index = 0
    for i, month in enumerate(month_list):
        if month != 'break':
            consecutive_count += 1
            total_months_paid += 1
            if consecutive_count > max_consecutive:
                max_consecutive = consecutive_count
                start_index = temp_start_index
                end_index = i
        else:
            consecutive_count = 0
            temp_start_index = i + 1

    # calculate the start and end date of the longest streak
    start_date = df['date'][start_index].date()
    end_date = (df['date'][end_index + 1] if end_index + 1 < len(df) else df['date'][end_index]).date()

    return max_consecutive, total_months_paid, start_date, end_date


def modify_crf_number(value):
    num_parts = value.split('-')
    if len(num_parts[0]) == 2:
        num = int(num_parts[0])
        num_parts[0] = '1999' if num >= 24 else '2000'
    return '-'.join(num_parts)

@st.cache_data
def scrape_fee_table(county, case_number, first_name, last_name, middle_name=''):
    scraper = CaseScraper(county, case_number, first_name, last_name, middle_name)
    return scraper.fee_table, scraper.fee_table_issued

def load_dataframes():
    alias_df = pd.read_csv("data/alias_output.csv")
    sentence_df = pd.read_csv("data/sentence_output.csv", dtype={'id': str, 'prison_sentence': float}, parse_dates=['conviction_date'])
    profile_df = pd.read_csv("data/profile_output.csv", dtype={'id': str}, parse_dates=['birthdate'])
    return alias_df, sentence_df, profile_df
def filter_alias_df(alias_df, first_name, last_name):
    first_name, last_name = first_name.lower(), last_name.lower()
    filtered_df = alias_df[alias_df['first_name'].str.lower().eq(first_name) & alias_df['last_name'].str.lower().eq(last_name)]
    return filtered_df.astype(str)

def filter_sentence_df(sentence_df, id):
    filtered_df = sentence_df[sentence_df['id'].eq(id)].astype(str)
    filtered_df['crf_number'] = filtered_df['crf_number'].apply(modify_crf_number)
    return filtered_df.reset_index(drop=True)

def search_profile(profile_df, id):
    filtered_df = profile_df[profile_df['id'].eq(id)]
    if len(filtered_df) > 0:
        status, facility = filtered_df.iloc[0][['status', 'facility']]
        official_last_name = filtered_df['last_name'].values[0]
        official_first_name = filtered_df['first_name'].values[0]
        official_middle_name = filtered_df['middle_name'].values[0] if 'middle_name' in filtered_df.columns else None

    else:
        status, facility = 'ID not found', 'ID not found'
    return status, facility, official_last_name, official_first_name, official_middle_name, filtered_df.reset_index(drop=True)

alias_df, sentence_df, profile_df = load_dataframes()

st.title("Step 1: Search Client Name")
st.write("https://okoffender.doc.ok.gov/")

first_name = st.text_input("First name:")
last_name = st.text_input("Last name:")

if first_name and last_name:
    filtered_df = filter_alias_df(alias_df, first_name, last_name)
    st.write(filtered_df)

st.title("Step 2: Get Offender Recprd")
st.write("https://okoffender.doc.ok.gov/")
id = st.text_input("Client ID:")

if id:
    id = str(id).zfill(10)
    filtered_sentence_df = filter_sentence_df(sentence_df, id)
    st.write(filtered_sentence_df)

    status, facility, official_last_name, official_first_name, official_middle_name, filtered_profile_df = search_profile(profile_df, id)
    st.write("Client Information:")
    st.write(filtered_profile_df)
    st.write(f"Status: {status}")
    st.write(f"Facility: {facility.title()}")

    unique_counties = filtered_sentence_df['sentencing_court'].unique()
    unique_cases = filtered_sentence_df['crf_number'].unique()

    st.write(f"Unique Counties: {', '.join(unique_counties)}")
    st.write(f"Unique Cases: {', '.join(unique_cases)}")

st.title("Step 3: See Fee Payments")

if 'filtered_sentence_df' in locals():
    # Add a new column with default value of False
    filtered_sentence_df.insert(0, 'selected', False)
    filtered_sentence_df = filtered_sentence_df[['selected', 'sentencing_court', 'crf_number']].drop_duplicates().reset_index(drop=True)

    def create_data_editor(filtered_sentence_df):
        return st.experimental_data_editor(
            filtered_sentence_df,
            use_container_width=True,
            num_rows="dynamic",
        )

    def process_selected_data(edited_df, scrape_fee_table, calculate_total_fees, calculate_consecutive_months):
        keep_rows = edited_df.loc[edited_df['selected'] == True].index.tolist()
        case_list = edited_df.loc[keep_rows, 'crf_number'].tolist()
        county_list = edited_df.loc[keep_rows, 'sentencing_court'].tolist()

        result = []

        for case_number, county in zip(case_list, county_list):
            county = county.split()[0]
            fee_table, fee_table_issued = scrape_fee_table(county, case_number, official_first_name, official_last_name,
                                             official_middle_name)
            time.sleep(1)

            total_fees_paid = round(calculate_total_fees(fee_table), 2)
            total_fees_issued = round(calculate_total_fees(fee_table_issued), 2)
            max_consecutive, total_months_paid, start_date, end_date = calculate_consecutive_months(fee_table)

            result.append({
                "case_number": case_number,
                "fee_table_paid": fee_table,
                "total_fees_paid": total_fees_paid,
                "total_months_paid": total_months_paid,
                "max_consecutive": max_consecutive,
                "start_date": start_date,
                "end_date": end_date,
                "fee_table_issued": fee_table_issued,
                "total_fees_issued": total_fees_issued
            })

            fee_table.to_csv("fee_table.csv", index=False)

        return result

    def display_results(results):
        for res in results:
            st.markdown(f"**Case Number: {res['case_number']}**")
            st.write(res["fee_table_issued"])
            st.write("Total Fees Issued: ", res["total_fees_issued"])
            st.write(res["fee_table_paid"])
            st.write("Total Fees Paid: ", res["total_fees_paid"])
            st.write("Total Months Paid: ", res["total_months_paid"])
            st.write("Consecutive Months Paid: ", res["max_consecutive"])
            st.write("Consecutive Months Start: ", res["start_date"])
            st.write("Consecutive Months End: ", res["end_date"])
            st.write("")

    edited_df = create_data_editor(filtered_sentence_df)

    if st.button("Done selecting? Click here to pull data."):
        results = process_selected_data(edited_df, scrape_fee_table, calculate_total_fees, calculate_consecutive_months)
        display_results(results)





# # Cache the data for faster retrieval
# @st.cache_data
# def scrape_multiple_cases(url_list, first_name, last_name, middle_name):
#     # Create a list to store the fee tables
#     fee_table_list = []
#
#     # Loop through the URLs and create an instance of the OSCNCaseScraper class for each URL
#     for url in url_list:
#         scraper = OSCNCaseScraper(url, first_name, last_name, middle_name)
#         try:
#             fee_table_list.append(scraper.fee_table)
#             st.write(f"{scraper.case_number}: {len(scraper.fee_table)} results")
#         except:
#             st.write(f"{scraper.case_number}: 0 results")
#
#     # Concatenate the fee tables into one overall fee table
#     overall_fee_table = pd.concat(fee_table_list)
#     # Convert the date column to datetime and extract just the date portion
#     overall_fee_table['date'] = pd.to_datetime(overall_fee_table['date']).dt.date
#     # Sort the fee table by date
#     overall_fee_table.sort_values(by='date', inplace=True)
#
#     return overall_fee_table.reset_index(drop=True)
#
# # Define a function to format the date
# def format_date(date_str):
#     date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
#     formatted_date = date_obj.strftime('%Y-%m-%d')
#     return formatted_date
#
# # Cache the data for faster retrieval
# @st.cache_data
# def get_data(first_name, last_name, middle_name='', db='all') -> pd.DataFrame:
#     docket_scraper = OSCNDocketScraper(db='all', first_name='Leroy', last_name='Jordan', middle_name='Albert')
#     results = docket_scraper.scrape_results()
#     # Convert the date_filed column to datetime and extract just the date portion
#     results['date_filed'] = pd.to_datetime(results['date_filed']).dt.date
#     # Insert a 'keep' column with all values initially set to True
#     results.insert(0, 'keep', False)
#     return results.reset_index(drop=True)
#
# # Create a Streamlit app
# st.title("Fines & Fees Waiver Automation")
#
# st.subheader("Enter Name")
# st.markdown("Please enter first name, middle name, and last name separated by commas (e.g. John,Michael,Smith), then press enter.")
#
# # Create a text input field for the user to enter their name
# name_input = st.text_input("")
#
# # Parse the name input into first name, middle name, and last name
# if name_input:
#     name_parts = name_input.split(",")
#     first_name = name_parts[0].strip()
#     middle_name = name_parts[1].strip()
#     last_name = name_parts[2].strip()
#
#     df = get_data(first_name, last_name, middle_name)
#     # Use the experimental data editor to allow the user to select which rows to keep
#     edited_df = st.experimental_data_editor(
#         df.drop(columns=['url']),
#         use_container_width=True,
#         num_rows="dynamic",
#     )
#
#     if st.button("Done selecting? Click here to pull data."):
#         # Get the indices of the rows that the user wants to keep
#         keep_rows = edited_df.loc[edited_df['keep'] == True].index.tolist()
#         # Get the corresponding URLs from the original dataframe
#         url_list = df.loc[keep_rows, 'url'].tolist()
#
#         st.write(url_list)
#         fee_tables = scrape_multiple_cases(url_list, first_name, last_name, middle_name)
#         st.write(fee_tables)
#
