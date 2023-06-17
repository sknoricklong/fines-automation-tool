import requests
import streamlit as st
from bs4 import BeautifulSoup
import pandas as pd
from io import BytesIO

from data_processing import *

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

def format_county(county):
    county = county.replace(" COUNTY COURT", "")
    return county.title()


def generate_excel_content(results, summary, case_list, url_list):
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
        streak_length, total_paid_months, _, total_amount_paid, total_amount_owed, _, _, fee_table_paid, fee_table_issued = result
        receipts_table = None

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
        individual_case_summaries = pd.concat([individual_case_summaries, case_info_df], ignore_index=True)

        # Append fee_table_paid to the combined DataFrame
        if fee_table_paid is not None:
            combined_fee_table_paid = pd.concat([combined_fee_table_paid, fee_table_paid], ignore_index=True)

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
            streak_length, total_paid_months, _, total_amount_paid, total_amount_owed, _, _, fee_table_paid, fee_table_issued = result
            receipts_table = None

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