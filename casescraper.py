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
        self.response = httpx.get(f"https://www.oscn.net/dockets/GetCaseInformation.aspx?db={self.county}&number=CF-{self.case_number}")
        self.soup = BeautifulSoup(self.response.content, "html.parser")
        self.tables = self.soup.find_all("table", class_="docketlist ocis")
        self.case_table = self.soup.find('table', class_='caseStyle')
        self.date = []
        self.docket_code = []
        self.description = []
        self.amount = []
        self.fee_table, self.fee_table_issued = self.extract_fee_table(self.soup, self.case_number, self.first_name, self.last_name, self.middle_name)

    def extract_fee_table(self, soup, case_number, first_name, last_name, middle_name):
        # Find all tables with class "docketlist ocis"
        tables = soup.find_all("table", class_="docketlist ocis")
        # Find the table with class "caseStyle"
        case_table = soup.find('table', class_='caseStyle')
        data = []
        for table in tables:
            # Find all rows with class "docketRow oddRow primary-entry" or "docketRow evenRow primary-entry"
            rows = table.select('tr.docketRow.oddRow.primary-entry, tr.docketRow.evenRow.primary-entry')

            for row in rows:
                # Extract the date from the first <td> tag
                date = row.find('td').text.strip()
                if re.match(r'\d{2}-\d{2}-\d{4}', date):
                    # Extract the docket code from the <font> tag with class "docket_code"
                    docket_code = row.find('font', class_='docket_code').text.strip()

                    # Extract the description from the <td> tag with class "description-wrapper"
                    description = row.find(class_='description-wrapper').text.strip()
                    description = re.sub(r'\s+', ' ', description)

                    # Extract the party name from the <span> tag with class "partyname"
                    party = [p.text.strip() for p in row.find_all(class_='partyname') if p is not None]
                    party = ' '.join(party)

                    # Extract the amount from the <td> tag with valign="top" and align="right"
                    amount = row.find('td', valign='top', align='right').text.strip().replace('$', '')

                    # Add the data as a tuple to the list
                    data.append((case_number, date, docket_code, description, party, amount))

        # Create a DataFrame from the list of tuples
        fee_table = pd.DataFrame(data, columns=['case_number', 'date', 'docket_code', 'description', 'party', 'amount'])
        fee_table['date'] = pd.to_datetime(fee_table['date'])

        # Extract the full name of the party from first, last, and middle names
        name = f"{last_name}, {first_name} {middle_name}".strip().lower()
        fee_table = fee_table[fee_table['party'].str.lower()==name]

        fee_table_issued = fee_table[fee_table["amount"].str.contains('\d')]
        fee_table_issued['amount'] = fee_table_issued['amount'].str.replace('[ ,$]', '', regex=True).astype(float)

        # Filter the fee table by docket code and party name
        fee_table = fee_table[
            (fee_table['docket_code'].isin(['ACCOUNT', 'PAY']))]

        # Extract the dollar amount from the description column using regular expressions
        pattern = r'TOTAL AMOUNT PAID:\s*\$?\s*(\d+\.\d{2})'
        fee_table['amount'] = fee_table['description'].str.extract(pattern)

        # Convert the amount column to float
        fee_table['amount'] = fee_table['amount'].str.replace('$', '', regex=True).astype(float)

        # Drop rows where the amount column is NaN or $0.00
        fee_table = fee_table.dropna(subset=['amount'])
        fee_table = fee_table[fee_table['amount'] > 0]

        return fee_table.reset_index(drop=True), fee_table_issued.reset_index(drop=True)