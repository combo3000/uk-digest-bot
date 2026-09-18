import feedparser
import requests
import json
import os
import time
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from google import genai
import yfinance as yf

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

with open("subscribers.json", "r") as f:
    data = json.load(f)
ALL_CHAT_IDS = data.get("subscribers", [])
print(f"Підписників: {len(ALL_CHAT_IDS)}")

# ─── ЗВЕРТАННЯ (50 штук, щотижня нове) ──────────────────────────────────────
_G = [
    "пірате", "псе", "чуваку", "легендо", "командире", "капітане", "воїне",
    "детективе", "генію", "авантюристе", "вікінгу", "мандрівнику", "лицарю",
    "самураю", "шерифе", "космонавте", "шпигуне", "магістре", "герою",
    "чарівнику", "хакере", "архітекторе", "стратеге", "майстре", "сенсей",
    "ковбою", "корсаре", "бароне", "філософе", "алхіміку", "мисливцю",
    "провіднику", "оракуле", "титане", "патріарху", "вожде", "гросмейстере",
    "акуло", "вовче", "драконе", "фенікс", "леопарде", "орле", "ведмедю",
    "рисе", "яструбе", "пантеро", "бізоне", "соколе", "гладіаторе"
]
_week_seed = datetime.now(ZoneInfo("Europe/Kyiv")).isocalendar()[1]
random.seed(_week_seed)
GREETING = random.choice(_G)
random.seed()

# ─── ПОГОДА (Open-Meteo, без ключа) ─────────────────────────────────────────
WMO_CODES = {
    0: "ясно ☀️", 1: "переважно ясно 🌤️", 2: "мінлива хмарність ⛅", 3: "хмарно ☁️",
    45: "туман 🌫️", 48: "туман 🌫️",
    51: "мряка 🌦️", 53: "мряка 🌦️", 55: "мряка 🌦️",
    61: "дощ 🌧️", 63: "дощ 🌧️", 65: "сильний дощ 🌧️",
    71: "сніг 🌨️", 73: "сніг 🌨️", 75: "сильний сніг ❄️",
    80: "зливи 🌦️", 81: "зливи 🌦️", 82: "сильні зливи ⛈️",
    95: "гроза ⛈️", 96: "гроза з градом ⛈️", 99: "гроза з градом ⛈️",
}

def get_weather(lat, lon, tz_name):
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,weathercode",
            "timezone": tz_name
        }, timeout=10)
        d = r.json()["current"]
        temp = round(d["temperature_2m"])
        desc = WMO_CODES.get(d["weathercode"], "невідомо")
        return f"{temp}°C, {desc}"
    except Exception as e:
        print(f"Погода помилка ({tz_name}): {e}")
        return "недоступно"

weather_kyiv = get_weather(50.4501, 30.5234, "Europe/Kiev")
weather_barcelona = get_weather(41.3851, 2.1734, "Europe/Madrid")
print(f"Київ: {weather_kyiv} | Барселона: {weather_barcelona}")

# ─── АКЦІЇ ───────────────────────────────────────────────────────────────────
def get_stock(ticker, name, currency=""):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return f"{name}: н/д"
        price = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2] if len(hist) > 1 else price
        change = ((price - prev) / prev) * 100
        arrow = "📈" if change >= 0 else "📉"
        return f"{name}: {price:.2f}{currency} ({change:+.2f}%) {arrow}"
    except Exception as e:
        print(f"Акція {ticker} помилка: {e}")
        return f"{name}: н/д"

stocks = "\n".join([
    get_stock("CSL.AX",  "CSL",    " AUD"),
    get_stock("GRF.MC",  "Grifols"," EUR"),
    get_stock("4502.T",  "Takeda", " JPY"),
])
print(f"Акції:\n{stocks}")

# ─── RSS НОВИНИ ───────────────────────────────────────────────────────────────
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
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

for source_name, feeds in RSS_FEEDS.items():
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                link = entry.get("link", "")
                if link in seen_links:
                    continue
                seen_links.add(link)
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    if published < cutoff:
                        continue
                articles.append({
                    "source": source_name,
                    "title": entry.get("title", ""),
                    "link": link,
                    "summary": entry.get("summary", "")[:200],
                })
        except Exception as e:
            print(f"RSS помилка {feed_url}: {e}")

print(f"Статей: {len(articles)}")

# ─── ДАТА ЗА КИЇВСЬКИМ ЧАСОМ ─────────────────────────────────────────────────
kyiv_now = datetime.now(ZoneInfo("Europe/Kyiv"))
_months = ["січня","лютого","березня","квітня","травня","червня",
           "липня","серпня","вересня","жовтня","листопада","грудня"]
date_str = f"{kyiv_now.day} {_months[kyiv_now.month - 1]} {kyiv_now.year}"

# ─── ВІДПРАВКА ───────────────────────────────────────────────────────────────
if not articles:
    for cid in ALL_CHAT_IDS:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": "⚠️ Сьогодні не вдалося зібрати новини."})
else:
    articles_text = "\n".join([
        f"{i}. [{a['source']}] {a['title']}\n   {a['link']}"
        for i, a in enumerate(articles, 1)
    ])

    prompt = f"""Ти — редактор ранкового дайджесту. Пишеш ТІЛЬКИ українською. Сьогодні {date_str}.

Склади дайджест суворо за цією структурою:

1. ПРИВІТАННЯ
Добрий ранок, {GREETING}! Сьогодні {date_str}.

2. ПОГОДА 🌍
Київ: {weather_kyiv}
Барселона: {weather_barcelona}

3. НОВИНИ — обери 6 РІЗНИХ статей зі списку нижче:
- 3 міжнародні (геополітика, економіка, технології)
- 1 спорт
- 1 культура або наука
- 1 курйоз або незвичайна новина
Формат кожної: [емодзі] Заголовок українською — суть у 1-2 реченнях. Посилання на новому рядку.

4. РИНКИ 💹
{stocks}
Додай 1 речення контексту якщо є суттєвий рух котрогось з тикерів.

5. СЛОВО ДНЯ 📚
🇺🇦 Слово українською: [рідкісне або красиве слово] — [значення]
🇬🇧 Англійське (advanced): [слово] — [переклад + короткий приклад]
🇪🇸 Іспанське (базове): [слово] — [переклад + як вимовляється]

6. ФАКТ ДНЯ 🧠
Один захопливий та неочевидний факт про світ. 2-3 речення.

7. ЖАРТ ДНЯ 😄
Класичний короткий жарт або dad joke. Справжній, не придуманий.

8. МУДРІСТЬ ДНЯ ✨
Одна відома цитата з ім'ям автора.

━━━━━━━━━━━━━━━━━━
СТАТТІ ДЛЯ ВИБОРУ:
{articles_text}"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    digest = None

    for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        for attempt in range(2):
            try:
                print(f"Спроба {attempt + 1} з моделлю {model}...")
                response = client.models.generate_content(model=model, contents=prompt)
                digest = response.text
                print(f"✅ Успішно: {model}")
                break
            except Exception as e:
                print(f"❌ Помилка {model} спроба {attempt + 1}: {e}")
                time.sleep(15)
        if digest:
            break

    if not digest:
        digest = "❌ Gemini недоступний сьогодні."

    for cid in ALL_CHAT_IDS:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": cid,
                "text": digest[:4096],
                "disable_web_page_preview": True
            }
        )
        print(f"✅ Надіслано: {cid}")
