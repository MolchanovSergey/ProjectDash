import requests
from datetime import datetime


def get_cbr_key_rate():
    try:
        # Официальное API ЦБ РФ
        url = "https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1=01/01/2023&date_req2=31/12/2024&VAL_NM_RQ=R01235"
        response = requests.get(url)
        response.raise_for_status()

        # Парсинг XML (пример, актуальный парсинг зависит от структуры ответа)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'xml')
        last_record = soup.find_all('Record')[-1]
        rate = last_record.Value.text.strip()
        date = last_record['Date']

        return {
            'rate': float(rate.replace(',', '.')),
            'date': datetime.strptime(date, '%d.%m.%Y').strftime('%d.%m.%Y')
        }
    except Exception as e:
        print(f"Ошибка получения ставки: {str(e)}")
        return {'rate': 'Н/Д', 'date': 'Н/Д'}

rate_data = get_cbr_key_rate()

print(rate_data)