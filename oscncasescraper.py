import httpx
import re
import pandas as pd
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

class OSCNCaseScraper:
    def __init__(self, url, first_name, last_name, middle_name=""):
        self.first_name = first_name
        self.last_name = last_name
        self.middle_name = middle_name
        self.url = url
        self.case_number = self.extract_case_number(url)
        self.response = httpx.get(self.url)
        self.soup = BeautifulSoup(self.response.content, "html.parser")
        self.tables = self.soup.find_all("table", class_="docketlist ocis")
        self.case_table = self.soup.find('table', class_='caseStyle')
        self.date = []
        self.docket_code = []
        self.description = []
        self.amount = []
        self.extract_case_info()
        self.fee_table = self.extract_fee_table(self.soup, self.case_number, self.first_name, self.last_name, self.middle_name)

    def extract_case_number(self, url):
          parsed_url = urlparse(url)
          query_dict = parse_qs(parsed_url.query)

          case_number = query_dict.get('number', [''])[0]
          if '&' in case_number:
              case_number = case_number.split('&')[0]

          return case_number

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

        # Filter the fee table by docket code and party name
        fee_table = fee_table[
            (fee_table['docket_code'].isin(['ACCOUNT', 'PAY']))]

        fee_table = fee_table[fee_table['party'].str.lower()==name]

        # Extract the dollar amount from the description column using regular expressions
        pattern = r'TOTAL AMOUNT PAID:\s*\$?\s*(\d+\.\d{2})'
        fee_table['amount'] = fee_table['description'].str.extract(pattern)

        # Convert the amount column to float
        fee_table['amount'] = fee_table['amount'].str.replace('$', '', regex=True).astype(float)

        # Drop rows where the amount column is NaN or $0.00
        fee_table = fee_table.dropna(subset=['amount'])
        fee_table = fee_table[fee_table['amount'] > 0]

        return fee_table.reset_index(drop=True)

    def extract_case_info(self):
        # Extracting the case name
        first_td, second_td = self.case_table.find_all('td', attrs={'width': '50%'})
        text_list = [text.strip() for text in first_td.stripped_strings]
        self.case_name = ' '.join(text_list)

        # Extracting attorney information
        attorney_tags = self.soup.find_all('td', {'valign': 'top', 'width': '50%'})
        text_list = []
        for tag in attorney_tags:
            text = tag.get_text(separator=' ').replace('\xa0', ' ')
            text_list.append(text.strip())
        self.attorney_info = ' '.join(text_list)

        # Extracting the issue, file date, and judge
        second_text_list = [text.strip().replace(",", "") for text in second_td.stripped_strings][1:]
        second_text_list[0] = second_text_list[0].strip("()")
        self.issue = second_text_list[0]
        self.file_date = re.findall(r"Filed: (\d{2}\/\d{2}\/\d{4})", second_text_list[1])[0]
        closed_pattern = r"Closed: (\d{2}\/\d{2}\/\d{4})"
        closed_match = re.search(closed_pattern, second_text_list[1])
        if closed_match:
            self.closed_date = closed_match.group(1)
        else:
            self.closed_date = None

        self.file_date = re.findall(r"Filed: (\d{2}\/\d{2}\/\d{4})", second_text_list[1])[0]
        try:
            self.closed_date = re.findall(r"Closed: (\d{2}\/\d{2}\/\d{4})", second_text_list[2])[0]
            self.judge = second_text_list[3].replace("Judge: ", "")
        except IndexError:
            self.closed_date = None
            self.judge = second_text_list[2].replace("Judge: ", "")


        # Extracting plaintiffs and defendants
        party_sections = self.soup.find_all('h2', {'class': 'section party'})
        self.defendants = []
        self.plaintiffs = []
        for party in party_sections:
            party_text = []
            for p in party.find_next_siblings('p'):
                if p.find_previous_sibling('h2') == party:
                    party_text.append(p.get_text().strip())
                else:
                    break
            party_text = ' '.join(party_text)

            # Cleaning the party text
            party_text = re.sub(r'[\r\n\x0b\x0c\u2028\u2029\xa0]+', ' ', party_text)
            party_text = re.sub(r',\s*', ', ', party_text)

            # Splitting party text by Plaintiff/Defendant and extracting names
            plaintiff_defendant_regex = re.compile(r'(Plaintiff|Defendant)', re.IGNORECASE)
            party_split = plaintiff_defendant_regex.split(party_text)
            party_split = [x.strip(', ') for x in party_split]
            defendant = []
            plaintiff = None
            for i, s in enumerate(party_split):
                if re.search(r'Defendant', s, re.IGNORECASE):
                    if i > 0:
                        defendant.append(party_split[i - 1])
                elif re.search(r'Plaintiff', s, re.IGNORECASE):
                    if i > 0:
                        plaintiff = party_split[i - 1]

            # Appending defendants and plaintiffs
            self.defendants.append(defendant)
            self.plaintiffs.append(plaintiff)

        self.defendants = self.defendants[0]

        # # Find the case status
        # status_tags = self.soup.find_all('td', {'width': '20%', 'valign': 'top'})
        # for status_tag in status_tags:
        #     next_tag = status_tag.find_next_sibling()
        #
        # self.status = next_tag.get_text()

    def return_dfs(self):
        return pd.DataFrame({
            'defendants': self.defendants,
            'plaintiff': self.plaintiffs,
            'file_date': self.file_date,
            'issue': self.issue,
            'status': self.status,
            'judge': self.judge,
            'attorney_info': self.attorney_info
        }), self.fee_table