import feedparser
import requests
import os
from datetime import datetime, timedelta
from google import genai

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RSS_FEEDS = {
    "The Guardian": [
        "https://www.theguardian.com/world/rss",
        "https://www.theguardian.com/uk-news/rss",
        "https://www.theguardian.com/business/rss",
    ],
    "BBC News": [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "http://feeds.bbci.co.uk/news/business/rss.xml",
        "http://feeds.bbci.co.uk/news/technology/rss.xml",
    ],
    "The Times": [
        "https://www.thetimes.com/rss/world",
    ],
    "Financial Times": [
        "https://www.ft.com/rss/home",
    ],
}

articles = []
cutoff = datetime.now() - timedelta(hours=24)
for source_name, feeds in RSS_FEEDS.items():
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                    if published < cutoff:
                        continue
                articles.append({
                    "source": source_name,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:200],
                })
        except:
            pass

if not articles:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": "⚠️ Сьогодні не вдалося зібрати новини з RSS."},
    )
else:
    articles_text = ""
    for i, art in enumerate(articles, 1):
        articles_text += f"{i}. [{art['source']}] {art['title']}\n   {art['link']}\n   {art['summary']}\n\n"

    prompt = f"""Ти — персональний редактор ранкового дайджесту новин. Звертайся "сер".
Твоя аудиторія — українець, бізнесмен, якому цікаві:
- Геополітика та світова економіка
- Технології та AI
- Цікаві культурні та наукові теми
- Бізнес та фінанси
Стиль: стислий але з цифрами, живий, з елементами гумору. Пишеш українською.

Ось {len(articles)} статей з британських ЗМІ за сьогодні:

{articles_text}

Обери 5 найцікавіших. Для кожної напиши:
1. Емодзі-індикатор теми
2. Заголовок українською і основний зміст (коротко)
3. Чому це цікаво — 1-2 речення
4. Посилання

Формат — готове повідомлення для Telegram (простий текст, без Markdown).
На початку — привітання з датою, коротко погодою в Львові на сьогодні.
В кінці — одне прикольне речення, або мотивація або якийсь прийом ведуших шоу або афоризм. щось що підніме настрій та зарядить."""

   import time
    client = genai.Client(api_key=GEMINI_API_KEY)
    digest = None
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            digest = response.text
            break
        except Exception as e:
            if attempt < 4:
                time.sleep(30)
            else:
                digest = f"❌ Gemini недоступний після 5 спроб: {e}"

    if len(digest) > 4000:
        for i in range(0, len(digest), 4000):
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": digest[i:i+4000], "disable_web_page_preview": True},
            )
    else:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": digest, "disable_web_page_preview": True},
        )
