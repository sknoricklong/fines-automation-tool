import streamlit as st
from utils import *
from data_processing import *
from web_navigation import *

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

    excel_content = generate_excel_content(results, {
        'Total Cases Searched': len(results),
        'Total Fees Issued': total_fees_issued_sum,
        'Total Fees Paid': total_fees_paid_sum,
        'Total Months Paid': total_months_paid_sum,
        'Max Consecutive Months Paid - Individual': max_consecutive_sum
    }, case_list, url_list)

    st.download_button(
        label="Download Excel",
        data=excel_content,
        file_name=f"{last_name}_{first_name}_.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )