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
print(f"Розсилка для {len(ALL_CHAT_IDS)} підписників")

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
    "The Times": ["https://www.thetimes.com/rss/world"],
    "Financial Times": ["https://www.ft.com/rss/home"],
}

# Збираємо статті — фільтруємо дублікати за посиланням
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

print(f"Зібрано {len(articles)} унікальних статей")

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
Твоя аудиторія — українці, бізнесмени.
Стиль: стислий, з цифрами де доречно, живий, з елементами гумору. Пишеш українською.

Ось {len(articles)} статей з британських ЗМІ за сьогодні:

{articles_text}

Обери рівно 6 РІЗНИХ статей за такою структурою:
- 3 міжнародні новини (геополітика, економіка, технології) — різні теми, не дублювати
- 1 спорт
- 1 культура або наука
- 1 щось незвичне або курйозне

ВАЖЛИВО: всі 6 статей мають бути про різні події. Не обирай дві статті про одну й ту саму подію.

Для кожної напиши:
1. Емодзі-індикатор теми
2. Заголовок українською і основний зміст (коротко, 1-2 речення)
3. ТІЛЬКИ якщо є корисне або цікаве трактування чи наслідок — додай 1 речення. Якщо немає — пропусти.
4. Посилання

Формат — готове повідомлення для Telegram (простий текст, без Markdown).
На початку — привітання з датою і коротко погодою в Львові.
В кінці — одне речення: афоризм, жарт ведучого або мотивація."""

    client = genai.Client(api_key=GEMINI_API_KEY)
    digest = None
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                digest = response.text
                break
            except Exception as e:
                print(f"{model_name} attempt {attempt+1}: {e}")
                if attempt < 2:
                    time.sleep(60)
        if digest:
            break

    if not digest:
        digest = "❌ Gemini недоступний сьогодні. Спробуємо завтра!"

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
