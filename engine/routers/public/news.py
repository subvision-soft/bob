import json
import os
from datetime import datetime, timedelta

from fastapi import APIRouter
from notion_client import Client

router = APIRouter()
notion_token = os.environ.get('NOTION_TOKEN')

notion_database_id = os.environ.get('NOTION_DATABASE_ID')
# Le cache à l'ancienne :)
news_cache = None


@router.get("/")
def get_news():
    global news_cache
    if news_cache is None or datetime.now() - news_cache["timestamp"] > timedelta(minutes=5):
        news_cache = fetch_news()
    return news_cache["data"]


def safe_get(data, dot_chained_keys):
    keys = dot_chained_keys.split('.')
    for key in keys:
        try:
            if isinstance(data, list):
                data = data[int(key)]
            else:
                data = data[key]
        except (KeyError, TypeError, IndexError):
            return None
    return data

def extract_news(notion_json):
    extracted_data = []
    for item in notion_json.get("results", []):
        properties = item.get("properties", {})
        title = properties.get("Titre", {}).get("title", [])
        title_text = title[0]["plain_text"] if title else ""
        date = properties.get("Date", {}).get("date", {}).get("start", "")
        date_obj = datetime.strptime(date, "%Y-%m-%d").date() if date else None
        illustration_files = properties.get("Illustration", {}).get("files", [])
        illustration = illustration_files[0]["file"]["url"] if illustration_files else ""
        description_rich_text = properties.get("Description", {}).get("rich_text", [])
        description_html = "".join([
            f"<b>{t['text']['content']}</b>" if t["annotations"]["bold"] else
            f"<i>{t['text']['content']}</i>" if t["annotations"]["italic"] else
            t["text"]["content"]
            for t in description_rich_text
        ]).replace("\n", "<br>")

        extracted_data.append({
            "title": title_text,
            "date": date_obj,
            "illustration": illustration,
            "description": description_html
        })

    return extracted_data

def fetch_news():
    client = Client(auth=notion_token)
    db_rows = client.databases.query(database_id=notion_database_id)
    notion_data = json.loads(json.dumps(db_rows))  # Replace with actual JSON
    parsed_data = extract_news(notion_data)
    return {
        "timestamp": datetime.now(),
        "data": parsed_data
    }