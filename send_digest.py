import feedparser
import requests
import json
import os
import time
from datetime import datetime, timedelta
from google import genai

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

with open("subscribers.json", "r") as f:
    data = json.load(f)
ALL_CHAT_IDS = data.get("subscribers", [])
print(f"Підписників: {len(ALL_CHAT_IDS)}")

RSS_FEEDS = {
    "The Guardian": [
        "https://www.theguardian.com/world/rss",
        "https://www.theguardian.com/uk-news/rss",
        "https://www.theguardian.com/business/rss",
        "https://www.theguardian.com/culture/rss",
        "https://www.theguardian.com/sport/rss",
        "https://www.theguardian.com/science/rss",
    ],
    "BBC News": [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "http://feeds.bbci.co.uk/news/business/rss.xml",
        "http://feeds.bbci.co.uk/news/technology/rss.xml",
        "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
        "http://feeds.bbci.co.uk/sport/rss.xml",
        "http://feeds.bbci.co.uk/news/science_environment/rss.xml",
    ],
    "Financial Times": ["https://www.ft.com/rss/home"],
}

articles = []
seen_links = set()
cutoff = datetime.now() - timedelta(hours=24)

for source_name, feeds in RSS_FEEDS.items():
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                link = entry.get("link", "")
                if link in seen_links:
                    continue
                seen_links.add(link)
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                    if published < cutoff:
                        continue
                articles.append({
                    "source": source_name,
                    "title": entry.get("title", ""),
                    "link": link,
                    "summary": entry.get("summary", "")[:200],
                })
        except:
            pass

print(f"Статей: {len(articles)}")

if not articles:
    for cid in ALL_CHAT_IDS:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": "⚠️ Сьогодні не вдалося зібрати новини."})
else:
    articles_text = "\n".join([f"{i}. [{a['source']}] {a['title']}\n   {a['link']}" for i, a in enumerate(articles, 1)])

    prompt = f"""Ти — редактор ранкового дайджесту. Звертайся "сер". Пишеш українською.

{len(articles)} статей:

{articles_text}

Обери 6 РІЗНИХ статей:
- 3 міжнародні (геополітика, економіка, технології)
- 1 спорт
- 1 культура/наука
- 1 курйоз

Формат кожної:
1. Емодзі
2. Заголовок + суть (1-2 речення)
3. Посилання

На початку — привітання з датою і погодою в Львові.
В кінці — афоризм або мотивація."""

    client = genai.Client(api_key=GEMINI_API_KEY)
    digest = None
    for model in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                digest = response.text
                break
            except:
                time.sleep(60)
        if digest:
            break

    if not digest:
        digest = "❌ Gemini недоступний сьогодні."

    for cid in ALL_CHAT_IDS:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": digest[:4000], "disable_web_page_preview": True})
