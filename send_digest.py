import feedparser
import requests
import json
import os
import time
import random
import concurrent.futures
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google import genai

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

# ── Env ────────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# ── Subscribers ────────────────────────────────────────────────────────────────
with open("subscribers.json", "r") as f:
    data = json.load(f)
ALL_CHAT_IDS = data.get("subscribers", [])
print(f"Підписників: {len(ALL_CHAT_IDS)}")

# ── Date / Time (Kyiv) ─────────────────────────────────────────────────────────
kyiv_now = datetime.now(ZoneInfo("Europe/Kyiv"))
_months = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]
date_str = f"{kyiv_now.day} {_months[kyiv_now.month - 1]} {kyiv_now.year}"

# ── Greeting — 100 titles, rotate every 3 days, no repeats until full cycle ────
_G = [
    # Морські / піратські
    "пірате", "корсаре", "капітане", "боцмане", "контрабандисте",
    "флібустьєре", "морський вовче", "адмірале", "штурмане", "юнге",
    # Хижаки / звірі
    "акуло", "вовче", "драконе", "орле", "пантеро",
    "яструбе", "соколе", "леопарде", "кобро", "крокодиле",
    "бізоне", "рисе", "гризлі", "ягуаре", "гієно",
    # Воїни
    "самураю", "вікінгу", "гладіаторе", "лицарю", "ніндзя",
    "берсеркере", "спартанцю", "мушкетере", "янічаре", "легіонере",
    "зрадливий асасине", "ронінe", "конкістадоре", "тамплієре", "мамлюке",
    # Магія / містика
    "чарівнику", "алхіміку", "некроманте", "друїде", "шамане",
    "астрологе", "ворожбите", "привиде", "демонологе", "оракуле",
    "чортополохе", "темний маге", "екзорцисте", "кабалісте", "чаклуне",
    # Авантюристи / шпигуни
    "детективе", "шпигуне", "хакере", "контрагенте", "диверсанте",
    "фальсифікаторе", "провокаторе", "авантюристе", "махінаторе", "конспіраторе",
    # Природні явища / рослини
    "огірочку", "метеорите", "торнадо", "вулкане", "цунамі",
    "пінгвіне", "броненосцю", "кактусе", "мандрагоро", "артишоку",
    "тайфуне", "блискавко", "айсберге", "лавино", "трюфелю",
    # Інтелектуали / лідери
    "генію", "стратеге", "титане", "гросмейстере", "магістре",
    "патріарху", "вожде", "провіднику", "архітекторе", "маестро",
    "філософе", "полемісте", "революціонере", "реформаторе", "інквізиторе",
    # Несподівані / кумедні
    "квасоле", "баклажане", "хом'яче", "єноте", "ламо",
    "камікадзе", "трампліне", "регуляторе", "галактичний мандрівниче", "суперзлодію",
]

def _get_greeting(dt: datetime) -> str:
    """Pick greeting: changes every 3 days, cycles through all titles without repeats.

    One fixed deterministic shuffle of the whole list, then we walk through it by
    global slot number. A full cycle = len(_G) * 3 days (≈10.5 months) with zero
    repeats. After that the same order repeats — intentionally, since a year+ gap
    makes any repeat feel fresh.
    """
    n = len(_G)
    epoch = datetime(2026, 1, 1, tzinfo=dt.tzinfo)   # fixed reference point
    slot  = (dt - epoch).days // 3                   # absolute slot (0, 1, 2, …)
    # One stable shuffle for all time — seed never changes
    rng = random.Random(0xD19E57)
    order = list(range(n))
    rng.shuffle(order)
    return _G[order[slot % n]]

GREETING = _get_greeting(kyiv_now)

# ── used.json ──────────────────────────────────────────────────────────────────
USED_FILE = "used.json"
try:
    with open(USED_FILE, "r", encoding="utf-8") as f:
        used = json.load(f)
except Exception:
    used = {}

ua_words_used  = used.get("ua_words", [])
en_words_used  = used.get("en_words", [])
es_words_used  = used.get("es_words", [])
jokes_used     = used.get("jokes", [])

# Keep only last 60 entries per list to avoid infinite growth
MAX_HISTORY = 60
ua_words_used = ua_words_used[-MAX_HISTORY:]
en_words_used = en_words_used[-MAX_HISTORY:]
es_words_used = es_words_used[-MAX_HISTORY:]
jokes_used    = jokes_used[-MAX_HISTORY:]

print(f"Історія: UA={len(ua_words_used)}, EN={len(en_words_used)}, ES={len(es_words_used)}, жарти={len(jokes_used)}")

# ── Weather ────────────────────────────────────────────────────────────────────
def get_weather(lat, lon, tz, city):
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,weathercode"
            f"&timezone={tz}"
        )
        r = requests.get(url, timeout=10)
        d = r.json()["current"]
        temp = round(d["temperature_2m"])
        code = d["weathercode"]
        if code == 0:
            icon = "☀️"
        elif code in (1, 2, 3):
            icon = "⛅" if code < 3 else "☁️"
        elif code in range(51, 68):
            icon = "🌧️"
        elif code in range(71, 78):
            icon = "❄️"
        elif code in range(80, 83):
            icon = "🌦️"
        elif code in range(95, 100):
            icon = "⛈️"
        else:
            icon = "🌡️"
        return f"🌍 {city}: {temp}°C {icon}"
    except Exception as e:
        return f"🌍 {city}: недоступно"

weather_kyiv      = get_weather(50.4501, 30.5234, "Europe%2FKiev",   "Київ")
weather_barcelona = get_weather(41.3851,  2.1734, "Europe%2FMadrid", "Барселона")

# ── Stocks ─────────────────────────────────────────────────────────────────────
def get_stock(ticker, label, currency):
    if not HAS_YFINANCE:
        return f"{label}: н/д"
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="2d")
        if hist.empty:
            return f"{label}: н/д"
        close = hist["Close"]
        price = close.iloc[-1]
        prev  = close.iloc[-2] if len(close) >= 2 else price
        chg   = price - prev
        pct   = (chg / prev * 100) if prev else 0
        arrow = "📈" if chg >= 0 else "📉"
        sign  = "+" if chg >= 0 else ""
        return f"{label}: {price:.2f}{currency} ({sign}{pct:.2f}%) {arrow}"
    except Exception:
        return f"{label}: н/д"

stocks_lines = "\n".join([
    get_stock("CSL.AX", "CSL",    " AUD"),
    get_stock("GRF.MC", "Grifols"," EUR"),
    get_stock("TAK",    "Takeda", " USD"),
])

# ── RSS feeds ──────────────────────────────────────────────────────────────────
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

articles   = []
seen_links = set()
cutoff     = kyiv_now - timedelta(hours=24)

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
                    if published < cutoff.replace(tzinfo=None):
                        continue
                articles.append({
                    "source":  source_name,
                    "title":   entry.get("title", ""),
                    "link":    link,
                    "summary": entry.get("summary", "")[:200],
                })
        except Exception:
            pass

print(f"Статей: {len(articles)}")

# ── Gemini prompt ──────────────────────────────────────────────────────────────
if not articles:
    for cid in ALL_CHAT_IDS:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": "⚠️ Сьогодні не вдалося зібрати новини."},
        )
else:
    articles_short = articles[:30]
    articles_text  = "\n".join(
        [f"{i}. [{a['source']}] {a['title']}\n   {a['link']}"
         for i, a in enumerate(articles_short, 1)]
    )

    # Build "already used" hints for Gemini
    ua_hint = ", ".join(ua_words_used[-20:]) if ua_words_used else "немає"
    en_hint = ", ".join(en_words_used[-20:]) if en_words_used else "немає"
    es_hint = ", ".join(es_words_used[-20:]) if es_words_used else "немає"
    jokes_hint = "; ".join(jokes_used[-10:]) if jokes_used else "немає"

    prompt = f"""Ти — редактор ранкового дайджесту. Звертайся "{GREETING}". Пишеш українською (крім оригінальних жартів).
Сьогодні {date_str}.

НЕ ВИКОРИСТОВУЙ markdown: ніяких **, ##, __, *, ---.

СУВОРО заборонено повторювати вже використані слова і жарти (вони вже були надіслані раніше):
• Вже використані українські слова: {ua_hint}
• Вже використані англійські слова: {en_hint}
• Вже використані іспанські слова: {es_hint}
• Вже використані жарти (початок): {jokes_hint}

Обов'язково обери НОВІ, яких немає в списку вище.

{len(articles_short)} статей для вибору:

{articles_text}

Склади дайджест у такому форматі (точно такі розділювачі):

Добрий ранок, {GREETING}!
Сьогодні {date_str}.

━━━ ПОГОДА ━━━
{weather_kyiv}
{weather_barcelona}

━━━ НОВИНИ ━━━
Обери 6 РІЗНИХ статей:
- 3 міжнародні (геополітика, економіка, технології) — різні теми
- 1 спорт
- 1 культура або наука
- 1 курйоз або незвичайна новина

Формат кожної новини:
ЕМОДЗІ Заголовок українською — коротке пояснення (1-2 речення).
URL

━━━ РИНКИ 💹 ━━━
{stocks_lines}

━━━ СЛОВО ДНЯ 📚 ━━━
🇺🇦 [НОВЕ рідкісне українське слово, якого немає вище] — переклад/пояснення
🇬🇧 [НОВЕ англійське слово рівня C1-C2, якого немає вище] — переклад | Приклад: речення
🇪🇸 [НОВЕ іспанське слово рівня A2-B1, якого немає вище] — переклад | Вимовляється: [транскрипція]

━━━ ФАКТ ДНЯ 🧠 ━━━
Один цікавий науковий або історичний факт (2-3 речення).

━━━ ЖАРТ ДНЯ 😄 ━━━
Короткий жарт або каламбур (dad joke), якого немає вище. Якщо знайшов англійською — залиш англійською. Якщо українською — залиш українською. Не придумуй — бери реальний відомий жарт.

Після жарту на окремому рядку напиши лише слова яких НЕ БУЛО вище у такому форматі (це потрібно для системи):
USED_UA: [точне українське слово яке обрав]
USED_EN: [точне англійське слово яке обрав]
USED_ES: [точне іспанське слово яке обрав]
USED_JOKE: [перші 60 символів жарту]"""

    # ── Call Gemini ────────────────────────────────────────────────────────────
    def call_gemini(mdl, prm):
        c = genai.Client(api_key=GEMINI_API_KEY)
        return c.models.generate_content(model=mdl, contents=prm).text

    digest = None
    for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        for attempt in range(2):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(call_gemini, model, prompt)
                    digest = future.result(timeout=90)
                print(f"✅ Gemini: {model}")
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

    # ── Parse USED_ lines and update used.json ─────────────────────────────────
    new_ua = new_en = new_es = new_joke = None
    clean_lines = []
    for line in digest.splitlines():
        if line.startswith("USED_UA:"):
            new_ua = line.split(":", 1)[1].strip()
        elif line.startswith("USED_EN:"):
            new_en = line.split(":", 1)[1].strip()
        elif line.startswith("USED_ES:"):
            new_es = line.split(":", 1)[1].strip()
        elif line.startswith("USED_JOKE:"):
            new_joke = line.split(":", 1)[1].strip()
        else:
            clean_lines.append(line)

    # Remove trailing blank lines from digest
    while clean_lines and not clean_lines[-1].strip():
        clean_lines.pop()
    digest_clean = "\n".join(clean_lines)

    # Update history
    if new_ua:
        ua_words_used.append(new_ua)
    if new_en:
        en_words_used.append(new_en)
    if new_es:
        es_words_used.append(new_es)
    if new_joke:
        jokes_used.append(new_joke)

    new_used = {
        "ua_words": ua_words_used[-MAX_HISTORY:],
        "en_words": en_words_used[-MAX_HISTORY:],
        "es_words": es_words_used[-MAX_HISTORY:],
        "jokes":    jokes_used[-MAX_HISTORY:],
    }

    try:
        with open(USED_FILE, "w", encoding="utf-8") as f:
            json.dump(new_used, f, ensure_ascii=False, indent=2)
        print(f"✅ used.json оновлено: UA={len(new_used['ua_words'])}, EN={len(new_used['en_words'])}, ES={len(new_used['es_words'])}, jokes={len(new_used['jokes'])}")

        # Git push used.json back to repo
        subprocess.run(["git", "config", "user.email", "digest-bot@github-actions"], check=True)
        subprocess.run(["git", "config", "user.name",  "Digest Bot"],               check=True)
        subprocess.run(["git", "add", USED_FILE],                                    check=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"chore: update used.json [{date_str}]"], check=True)
            subprocess.run(["git", "push"],                                          check=True)
            print("✅ used.json збережено в репозиторій")
        else:
            print("ℹ️ used.json без змін, пуш не потрібен")
    except Exception as e:
        print(f"⚠️ Не вдалося оновити used.json: {e}")

    # ── Send to Telegram ───────────────────────────────────────────────────────
    for cid in ALL_CHAT_IDS:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": cid,
                "text": digest_clean[:4096],
                "disable_web_page_preview": True,
            },
        )
    print("✅ Дайджест надіслано")
