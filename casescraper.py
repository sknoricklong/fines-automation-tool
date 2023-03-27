import httpx
import re
import pandas as pd
from bs4 import BeautifulSoup
import requests


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
        self.fee_table, self.fee_table_issued = self.extract_fee_table(self.soup, self.case_number, self.first_name,
                                                                       self.last_name, self.middle_name)

    def extract_fee_table(self, soup, case_number, first_name, last_name, middle_name=""):
        # Implementation of extract_fee_table method goes here
        pass

    def get_proxies(self):
        proxies_list = []

        c = requests.get("https://spys.me/proxy.txt")
        test_str = c.text
        a = re.finditer(r"[0-9]+(?:\.[0-9]+){3}:[0-9]+", test_str, re.MULTILINE)
        for i in a:
            proxies_list.append(i.group())

        c = requests.get("https://free-proxy-list.net/")
        soup = BeautifulSoup(c.content, 'html.parser')
        z = soup.find('textarea').get_text()
        x = re.findall(r"[0-9]+(?:\.[0-9]+){3}:[0-9]+", z)
        for proxy in x:
            proxies_list.append(proxy)

        return proxies_list

    def get_proxy(self):
        if not self.proxies_list:
            return None
        return self.proxies_list.pop()

    def make_request(self, url, proxy):
        if not proxy:
            return None

        proxies = {
            "http://": f"http://{proxy}",
            "https://": f"https://{proxy}"
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:106.0) Gecko/20100101 Firefox/106.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }

        try:
            with httpx.Client(proxies=proxies, headers=headers, timeout=5.0, verify=False) as client:
                response = client.get(url)
            return response
        except httpx.RequestError as exc:
            print(f"An error occurred while requesting {exc.request.url!r}: {exc}")
            return None

    def get_response(self):
        self.proxies_list = self.get_proxies()

        while True:
            proxy = self.get_proxy()

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