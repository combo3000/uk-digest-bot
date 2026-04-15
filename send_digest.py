import feedparser
import requests
import os
import time
from datetime import datetime, timedelta
from google import genai

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Додай chat_id друга сюди (через кому):
ALL_CHAT_IDS = [TELEGRAM_CHAT_ID]

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
    for cid in ALL_CHAT_IDS:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": "⚠️ Сьогодні не вдалося зібрати новини з RSS."},
        )
else:
    articles_text = ""
    for i, art in enumerate(articles, 1):
        articles_text += f"{i}. [{art['source']}] {art['title']}\n   {art['link']}\n   {art['summary']}\n\n"

    prompt = f"""Ти — персональний редактор ранкового дайджесту новин. Звертайся "сер".
Твоя аудиторія — українець, бізнесмен.
Стиль: стислий, з цифрами де доречно, живий, з елементами гумору. Пишеш українською.

Ось {len(articles)} статей з британських ЗМІ за сьогодні:

{articles_text}

Обери рівно 6 статей за такою структурою:
- 3 міжнародні новини (геополітика, економіка, технології)
- 1 спорт
- 1 культура/наука
- 1 щось незвичне або курйозне

Для кожної напиши:
1. Емодзі-індикатор теми
2. Заголовок українською і основний зміст (коротко, 1-2 речення)
3. ТІЛЬКИ якщо є корисне або цікаве трактування чи наслідок новини — додай його. Якщо немає — не пиши нічого зайвого.
4. Посилання

НЕ пиши "чому це важливо" або "чому це цікаво". Просто факти і суть.

Формат — готове повідомлення для Telegram (простий текст, без Markdown).
На початку — привітання з датою, коротко погодою в Львові на сьогодні.
В кінці — одне прикольне речення, або мотивація або якийсь прийом ведуших шоу або афоризм. щось що підніме настрій та зарядить."""

    client = genai.Client(api_key=GEMINI_API_KEY)
    digest = None
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]

    for model_name in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                digest = response.text
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(60)
                else:
                    digest = None
        if digest:
            break

    if not digest:
        digest = "❌ Gemini недоступний. Спробуй пізніше через кнопку в боті."

    for cid in ALL_CHAT_IDS:
        if len(digest) > 4000:
            for i in range(0, len(digest), 4000):
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": digest[i:i+4000], "disable_web_page_preview": True},
                )
        else:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": digest, "disable_web_page_preview": True},
            )
