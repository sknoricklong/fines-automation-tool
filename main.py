from datetime import datetime
import streamlit as st
import pandas as pd
import time
from casescraper import CaseScraper

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

@st.cache_data()
def scrape_fee_table(county, case_number, first_name, last_name, middle_name=''):
    scraper = CaseScraper(county, case_number, first_name, last_name, middle_name)
    return scraper.fee_table, scraper.fee_table_issued, scraper.url

def calculate_total_fees(df):
    return df['amount'].sum()

def calculate_consecutive_months(df):
    if len(df) == 0:
        return 0, 0, None, None

    # Ensure the date column is in datetime format
    df['date'] = pd.to_datetime(df['date'])

    # Set the date column as the index and resample to a monthly frequency
    df.set_index('date', inplace=True)
    df_monthly = df.resample('M').count().reset_index()

    # Create a custom function to find the longest streak of consecutive months
    def longest_streak(data):
        max_streak = 0
        current_streak = 0
        start_month = None
        end_month = None
        total_paid_months = 0

        for i, row in data.iterrows():
            if row[1] > 0:
                total_paid_months += 1
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
                    start_month_index = data.loc[i - max_streak + 1, 'date']
                    end_month_index = row['date']
                    start_month = df.loc[df.index >= start_month_index].first_valid_index()
                    end_month = df.loc[df.index <= end_month_index].last_valid_index()
            else:
                current_streak = 0

        return max_streak, start_month, end_month, total_paid_months

    # Calculate the longest streak of consecutive months and total paid months
    streak_length, streak_start, streak_end, total_paid_months = longest_streak(df_monthly)

    return streak_length, total_paid_months, streak_start, streak_end


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
    st.write(filtered_sentence_df)

    status, facility, official_last_name, official_first_name, official_middle_name, filtered_profile_df = search_profile(
        profile_df, id)
    st.write("Client Information:")
    st.write(filtered_profile_df)
    st.write(f"Status: {status}")
    st.write(f"Facility: {facility.title()}")

    unique_counties = filtered_sentence_df['sentencing_court'].unique()
    unique_cases = filtered_sentence_df['crf_number'].unique()

    st.write(f"Unique Counties: {', '.join(unique_counties)}")
    st.write(f"Unique Cases: {', '.join(unique_cases)}")
    # years_served = round(filtered_sentence_df['community_sentence'].sum(), 2)
    # st.write(f"Years Served: {str(years_served)}")

st.title("Step 3: Select Cases to Find Fees")
st.write("Source: https://www.oscn.net/")

if 'filtered_sentence_df' in locals():
    filtered_sentence_df.insert(0, 'selected', False)
    filtered_sentence_df = filtered_sentence_df[
        ['selected', 'sentencing_court', 'crf_number']].drop_duplicates().reset_index(drop=True)

    edited_df = st.experimental_data_editor(filtered_sentence_df, use_container_width=True, num_rows="dynamic")

    if st.button("Done selecting? Click here to pull data."):
        keep_rows = edited_df.loc[edited_df['selected'] == True].index.tolist()
        case_list = edited_df.loc[keep_rows, 'crf_number'].tolist()
        county_list = edited_df.loc[keep_rows, 'sentencing_court'].tolist()

        results = []

        for case_number, county in zip(case_list, county_list):
            case_number = case_number.split('CT')[0].strip()
            county = county.split()[0]
            try:
                fee_table, fee_table_issued, url = scrape_fee_table(county, case_number, official_first_name,
                                                                    official_last_name, official_middle_name)
            except ValueError as e:
                st.write(f"No case information found for {case_number}")
                continue

            time.sleep(1)

            total_fees_paid = round(calculate_total_fees(fee_table), 2)
            total_fees_issued = round(calculate_total_fees(fee_table_issued), 2)
            max_consecutive, total_months_paid, start_date, end_date = calculate_consecutive_months(fee_table)

            result = {
                "case_number": case_number,
                "url": url,
                "fee_table_paid": fee_table,
                "total_fees_paid": total_fees_paid,
                "total_months_paid": total_months_paid,
                "max_consecutive": max_consecutive,
                "start_date": start_date,
                "end_date": end_date,
                "fee_table_issued": fee_table_issued,
                "total_fees_issued": total_fees_issued
            }

            results.append(result)

        # Initialize summary variables
        total_fees_paid_sum = 0
        total_fees_issued_sum = 0
        total_months_paid_sum = 0
        max_consecutive_sum = 0

        for res in results:
            st.markdown(f"**Case Number: {res['case_number']}**")
            st.write("URL: ", res["url"])
            st.write("Total Fees Issued: ", res["total_fees_issued"])
            st.write(res["fee_table_issued"])
            st.write("Total Fees Paid: ", res["total_fees_paid"])
            st.write("Total Months Paid: ", res["total_months_paid"])
            st.write("Consecutive Months Paid: ", res["max_consecutive"])
            st.write("Consecutive Months Start: ", res["start_date"])
            st.write("Consecutive Months End: ", res["end_date"])
            st.write(res["fee_table_paid"])
            st.write("")

            # Update summary variables
            total_fees_paid_sum += res["total_fees_paid"]
            total_fees_issued_sum += res["total_fees_issued"]
            total_months_paid_sum += res["total_months_paid"]
            max_consecutive_sum = max(max_consecutive_sum, res["max_consecutive"])

        # Display summary
        st.title("Summary:")
        st.write("Total Cases Searched: ", len(results))
        st.write("Total Fees Issued: ",  total_fees_issued_sum)
        st.write("Total Fees Paid: ", total_fees_paid_sum)
        st.write("Total Months Paid: ", total_months_paid_sum)
        st.write("Max Consecutive Months Paid: ", max_consecutive_sum)

