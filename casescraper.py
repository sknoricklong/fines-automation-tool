import httpx
import re
import pandas as pd
from bs4 import BeautifulSoup

class CaseScraper:
    def __init__(self, county, case_number, first_name, last_name, middle_name=""):
        self.first_name = first_name
        self.last_name = last_name
        self.middle_name = middle_name
        self.county = county.split()[0]
        self.case_number = case_number
        self.url = f"https://www.oscn.net/dockets/GetCaseInformation.aspx?db={self.county}&number=CF-{self.case_number}"
        self.response = httpx.get(self.url)
        self.soup = BeautifulSoup(self.response.content, "html.parser")
        self.tables = self.soup.find_all("table", class_="docketlist ocis")
        self.case_table = self.soup.find('table', class_='caseStyle')
        self.date = []
        self.docket_code = []
        self.description = []
        self.amount = []
        self.fee_table, self.fee_table_issued = self.extract_fee_table(self.soup, self.case_number, self.first_name, self.last_name, self.middle_name)

    def extract_fee_table(self, soup, case_number, first_name, last_name, middle_name):
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

        try:
            # Convert first_name and last_name to lowercase
            first_name = first_name.lower()
            last_name = last_name.lower()

            if not fee_table['party'].empty:
                # Filter the fee_table dataframe based on party column
                fee_table = fee_table[
                    fee_table['party'].str.lower().str.contains(first_name) &
                    fee_table['party'].str.lower().str.contains(last_name)
                    ]
        except AttributeError as e:
            pass

        fee_table_issued = fee_table[fee_table["amount"].str.contains('\d')]
        fee_table_issued.loc[:, 'amount'] = fee_table_issued['amount'].str.replace('[ ,$]', '', regex=True).astype(
            float)

        # Filter the fee table by docket code and party name
        fee_table = fee_table[
            (fee_table['code'].isin(['ACCOUNT', 'PAY']))]

        # Extract the dollar amount from the description column using regular expressions
        pattern = r'TOTAL AMOUNT PAID:\s*\$?\s*(\d+\.\d{2})'
        fee_table['amount'] = fee_table['description'].str.extract(pattern)

        # Convert the amount column to float
        fee_table['amount'] = fee_table['amount'].str.replace('$', '', regex=True).astype(float)

        # Drop rows where the amount column is NaN or $0.00
        fee_table = fee_table.dropna(subset=['amount'])
        fee_table = fee_table[fee_table['amount'] > 0]

        return fee_table.reset_index(drop=True), fee_table_issued.reset_index(drop=True)