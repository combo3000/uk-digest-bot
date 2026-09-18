import feedparser
import requests
import json
import os
import time
import random
import concurrent.futures
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from google import genai

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("⚠️ yfinance не встановлено")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

with open("subscribers.json", "r") as f:
    data = json.load(f)
ALL_CHAT_IDS = data.get("subscribers", [])
print(f"Підписників: {len(ALL_CHAT_IDS)}")

# ─── ДАТА (обчислюємо одразу, до всього іншого) ──────────────────────────────
kyiv_now = datetime.now(ZoneInfo("Europe/Kyiv"))
_months = ["січня","лютого","березня","квітня","травня","червня",
           "липня","серпня","вересня","жовтня","листопада","грудня"]
date_str = f"{kyiv_now.day} {_months[kyiv_now.month - 1]} {kyiv_now.year}"
print(f"Дата: {date_str}")

# ─── ЗВЕРТАННЯ (50 штук, щотижня нове) ──────────────────────────────────────
_G = [
    # Морські/пригодницькі
    "пірате", "корсаре", "капітане", "боцмане", "контрабандисте",
    # Тварини
    "акуло", "вовче", "драконе", "орле", "пантеро",
    "яструбе", "соколе", "леопарде", "кобро", "крокодиле",
    "бізоне", "рисе",
    # Воїни/герої
    "самураю", "вікінгу", "гладіаторе", "лицарю", "ніндзя",
    "берсеркере", "спартанцю", "мушкетере", "янічаре",
    # Містика/фантастика
    "чарівнику", "алхіміку", "некроманте", "друїде", "шамане",
    "астрологе", "ворожбите", "чортополохе", "привиде",
    # Детективи/агенти
    "детективе", "шпигуне", "хакере",
    # Екстравагантні
    "огірочку", "метеорите", "торнадо", "вулкане", "цунамі",
    "пінгвіне", "броненосцю", "кактусе", "мандрагоро", "артишоку",
    # Статусні/класичні
    "генію", "стратеге", "оракуле", "титане", "гросмейстере",
    "магістре", "патріарху", "вожде", "провіднику",
]
_week_seed = kyiv_now.isocalendar()[1]
random.seed(_week_seed)
GREETING = random.choice(_G)
random.seed()
print(f"Звертання цього тижня: {GREETING}")

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

def get_weather(lat, lon, tz_name, city):
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,weathercode",
            "timezone": tz_name
        }, timeout=10)
        d = r.json()["current"]
        temp = round(d["temperature_2m"])
        desc = WMO_CODES.get(d["weathercode"], "невідомо")
        print(f"Погода {city}: {temp}°C, {desc}")
        return f"{temp}°C, {desc}"
    except Exception as e:
        print(f"Погода помилка {city}: {e}")
        return "недоступно"

weather_kyiv = get_weather(50.4501, 30.5234, "Europe/Kiev", "Київ")
weather_barcelona = get_weather(41.3851, 2.1734, "Europe/Madrid", "Барселона")

# ─── АКЦІЇ ───────────────────────────────────────────────────────────────────
def get_stock(ticker, name, currency=""):
    if not HAS_YFINANCE:
        return f"{name}: н/д"
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            print(f"Акція {name} ({ticker}): порожня відповідь")
            return f"{name}: н/д"
        price = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2] if len(hist) > 1 else price
        change = ((price - prev) / prev) * 100
        arrow = "📈" if change >= 0 else "📉"
        result = f"{name}: {price:.2f}{currency} ({change:+.2f}%) {arrow}"
        print(f"Акція: {result}")
        return result
    except Exception as e:
        print(f"Акція {ticker} помилка: {e}")
        return f"{name}: н/д"

stocks = "\n".join([
    get_stock("CSL.AX", "CSL",    " AUD"),
    get_stock("GRF.MC", "Grifols"," EUR"),
    get_stock("TAK",    "Takeda", " USD"),  # TAK — NYSE ADR, надійніший
])

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

print(f"Статей зібрано: {len(articles)}")

# ─── ВІДПРАВКА ───────────────────────────────────────────────────────────────
if not articles:
    for cid in ALL_CHAT_IDS:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": "⚠️ Сьогодні не вдалося зібрати новини."})
else:
    articles_short = articles[:30]
    articles_text = "\n".join([
        f"{i}. [{a['source']}] {a['title']}\n   {a['link']}"
        for i, a in enumerate(articles_short, 1)
    ])

    prompt = (
        "Ти редактор ранкового дайджесту. Відповідай ТІЛЬКИ українською мовою.\n"
        "ВАЖЛИВО: не використовуй markdown — жодних **, ##, *, _, ~. Тільки звичайний текст і емодзі.\n\n"
        f"Перший рядок повідомлення — ТОЧНО такий (не змінюй жодного символу):\n"
        f"Добрий ранок, {GREETING}! Сьогодні {date_str}.\n\n"
        "Далі склади дайджест за цим шаблоном (всі розділи обов'язкові):\n\n"
        "━━━ ПОГОДА ━━━\n"
        f"🌍 Київ: {weather_kyiv}\n"
        f"🌍 Барселона: {weather_barcelona}\n\n"
        "━━━ НОВИНИ ━━━\n"
        "Обери 6 статей зі списку нижче: 3 міжнародні (геополітика/економіка/технології), 1 спорт, 1 наука або культура, 1 курйоз.\n"
        "Формат кожної новини:\n"
        "[емодзі] Назва українською — суть у 1-2 реченнях.\n"
        "[пряме посилання]\n\n"
        "━━━ РИНКИ 💹 ━━━\n"
        f"{stocks}\n\n"
        "━━━ СЛОВО ДНЯ 📚 ━━━\n"
        "🇺🇦 [рідкісне або красиве українське слово] — [значення]\n"
        "🇬🇧 [advanced англійське слово] — [переклад українською] | Приклад: [речення]\n"
        "🇪🇸 [іспанське слово рівня A2-B1] — [переклад українською] | Вимовляється: [транскрипція] | Приклад: [коротке речення іспанською]\n\n"
        "━━━ ФАКТ ДНЯ 🧠 ━━━\n"
        "[один неочевидний і захопливий факт, 2-3 речення]\n\n"
        "━━━ ЖАРТ ДНЯ 😄 ━━━\n"
        "[one short dad joke or pun IN ENGLISH — original English only, no translation, wordplay must work]\n\n"
        "СТАТТІ ДЛЯ ВИБОРУ:\n"
        f"{articles_text}"
    )

    def call_gemini(mdl, prm):
        c = genai.Client(api_key=GEMINI_API_KEY)
        response = c.models.generate_content(model=mdl, contents=prm)
        return response.text

    digest = None
    for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        for attempt in range(2):
            try:
                print(f"Спроба {attempt + 1} з моделлю {model}...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(call_gemini, model, prompt)
                    digest = future.result(timeout=90)
                print(f"✅ Gemini успішно: {model}")
                break
            except concurrent.futures.TimeoutError:
                print(f"⏱️ Timeout {model} спроба {attempt + 1}")
            except Exception as e:
                print(f"❌ Помилка {model} спроба {attempt + 1}: {e}")
            time.sleep(5)
        if digest:
            break

    if not digest:
        digest = "❌ Gemini недоступний сьогодні."

    print(f"Розмір дайджесту: {len(digest)} символів")

    for cid in ALL_CHAT_IDS:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": cid,
                "text": digest[:4096],
                "disable_web_page_preview": True
            }
        )
        print(f"Telegram {cid}: {r.status_code}")
