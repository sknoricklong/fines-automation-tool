import httpx
import pandas as pd
from bs4 import BeautifulSoup


class OSCNDocketScraper:
    def __init__(self, db='all', first_name='', last_name='', middle_name=''):
        self.db = db
        self.first_name = first_name
        self.last_name = last_name
        self.middle_name = middle_name

    def get_soup(self):
        url = f'https://www.oscn.net/dockets/Results.aspx?db={self.db}&number=&lname={self.last_name}&fname={self.first_name}&mname={self.middle_name}&DoBMin=&DoBMax=&partytype=&apct=&dcct=&FiledDateL=&FiledDateH=&ClosedDateL=&ClosedDateH=&iLC=&iLCType=&iYear=&iNumber=&citation='
        response = httpx.get(url)
        soup = BeautifulSoup(response.content, "html.parser")
        return soup

    def scrape_results(self):
        soup = self.get_soup()
        rows = soup.find_all('tr', class_=lambda x: x and 'resultTableRow' in x and ('oddRow' in x or 'evenRow' in x))

        # Create an empty list to store dictionaries of td texts
        data = []

        # Loop over each row
        for row in rows:
            # Create a dictionary for the row
            row_data = {}

            # Loop over each td element in the row
            for i, cell in enumerate(row.find_all('td')):
                # If this is the first td element, extract the link and add it as the final column
                if i == 0:
                    link = cell.find('a')['href']
                    link = 'https://www.oscn.net/dockets/' + link
                    row_data[len(row.find_all('td'))] = link
                # Add the text of the td element to the dictionary with the column index as the key
                row_data[i] = cell.text.strip()
            # Append the row data to the list
            data.append(row_data)

        # Create a DataFrame from the list of dictionaries
        df = pd.DataFrame(data)

        # Rename the final column to 'Link'
        df.columns = ['url', 'case_number', 'date_filed', 'case_name', 'found_party']
        df = df.drop_duplicates(subset=['case_number'])
        df['date_filed'] = pd.to_datetime(df['date_filed'])
        df.sort_values(by='date_filed')

        return df