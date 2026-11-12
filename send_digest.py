"""
UK Morning Digest — щоранковий дайджест у Telegram.

Запуск: GitHub Actions. Основний тригер — cron-job.org о 08:00 за Києвом
(workflow_dispatch через GitHub API), резервний — schedule у digest.yml.

MODE=normal — всім підписникам, не частіше одного разу на день (last_sent у used.json).
MODE=test   — тільки першому підписнику зі списку, без збереження історії.
"""

import difflib
import html
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import feedparser
import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

KYIV = ZoneInfo("Europe/Kyiv")
USED_FILE = "used.json"
MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-lite-latest"]
HISTORY_LIMITS = {"jokes": 200, "facts": 120, "motivations": 60, "numbers": 60}
PER_SOURCE = 12                 # скільки статей з одного видання показуємо моделі
FRESH = timedelta(hours=36)     # Economist публікує рідше, тому вікно ширше за 24 год
FRESH_OVERRIDE = {"Der Spiegel": timedelta(hours=96), "Nature": timedelta(hours=72)}  # рідкісні стрічки
MAX_PER_OUTLET = 3              # не більше 3 статей з одного видання в дайджесті

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
WEEKDAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]

# ── Джерела ───────────────────────────────────────────────────────────────────
SOURCES = {
    "The Economist": [
        ("головне", "https://www.economist.com/latest/rss.xml"),
        ("світ", "https://www.economist.com/international/rss.xml"),
        ("бізнес", "https://www.economist.com/business/rss.xml"),
        ("економіка", "https://www.economist.com/finance-and-economics/rss.xml"),
        ("наука", "https://www.economist.com/science-and-technology/rss.xml"),
        ("культура", "https://www.economist.com/culture/rss.xml"),
    ],
    "NYT": [
        ("світ", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
        ("бізнес", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
        ("технології", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
        ("наука", "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml"),
        ("культура", "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml"),
        ("спорт", "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml"),
    ],
    "FT": [
        ("головне", "https://www.ft.com/rss/home"),
        ("світ", "https://www.ft.com/world?format=rss"),
        ("компанії", "https://www.ft.com/companies?format=rss"),
    ],
    "The Guardian": [
        ("світ", "https://www.theguardian.com/world/rss"),
        ("бізнес", "https://www.theguardian.com/business/rss"),
        ("наука", "https://www.theguardian.com/science/rss"),
        ("культура", "https://www.theguardian.com/culture/rss"),
        ("спорт", "https://www.theguardian.com/sport/rss"),
    ],
    "BBC": [
        ("світ", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("бізнес", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("технології", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
        ("наука", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
        ("культура", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"),
        ("спорт", "https://feeds.bbci.co.uk/sport/rss.xml"),
    ],
    "Der Spiegel": [
        ("світ", "https://www.spiegel.de/international/index.rss"),
    ],
    "Le Monde": [
        ("головне", "https://www.lemonde.fr/en/rss/une.xml"),
        ("культура", "https://www.lemonde.fr/en/culture/rss_full.xml"),
    ],
    "Wired": [
        ("технології", "https://www.wired.com/feed/rss"),
        ("наука", "https://www.wired.com/feed/category/science/latest/rss"),
    ],
    "Nature": [
        # у стрічці і новини, і наукові статті — беремо лише новини (адреси з d41586)
        ("наука", "https://www.nature.com/nature.rss", r"/articles/d41586"),
    ],
    "The Atlantic": [
        ("головне", "https://www.theatlantic.com/feed/all/"),
        ("культура", "https://www.theatlantic.com/feed/channel/culture/"),
    ],
    "El País": [
        ("Іспанія", "https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada"),
    ],
}
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) UKDigestBot/2.0 (+https://github.com/combo3000/uk-digest-bot)"}

# ── Звертання — змінюється кожні 3 дні, без повторів до кінця кола ─────────────
GREETINGS = [
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
    "зрадливий асасине", "роніне", "конкістадоре", "тамплієре", "мамлюке",
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


def get_greeting(dt):
    """Одне стабільне перемішування списку; крок — 3 дні; повне коло без повторів."""
    slot = (dt - datetime(2026, 1, 1, tzinfo=dt.tzinfo)).days // 3
    order = list(range(len(GREETINGS)))
    random.Random(0xD19E57).shuffle(order)
    return GREETINGS[order[slot % len(GREETINGS)]]


# ── Креативні «замовлення» на день: різноманітність замість топ-25 dad jokes ──
JOKE_FORMATS = [
    "анекдот-діалог на 3–8 реплік",
    "міні-історія з несподіваним фіналом (4–8 речень)",
    "сухий британський однорядковий гумор",
    "абсурдний анекдот",
    "одеський анекдот",
    "жарт-спостереження в стилі стендапу (3–6 речень)",
    "чорний гумор без жорстокості й образ груп людей",
    "офісний або бюрократичний анекдот",
    "розумний каламбур, якого немає в топ-списках інтернету",
    "жарт у формі оголошення, листа або інструкції",
    "анекдот про Шерлока Холмса і доктора Ватсона",
    "анекдот формату «приходить … до …»",
    "жарт про переговори або контракт",
    "інтелектуальний жарт для тих, хто читає The Economist",
]
JOKE_TOPICS = [
    "кіт", "економіст", "бухгалтер", "фармацевт", "лікар", "митниця", "логістика",
    "бабуся", "програміст", "штучний інтелект", "філософ", "рибалка", "теща",
    "футбол", "вино", "ресторан і офіціант", "студент та іспит", "професор",
    "британці та погода", "іспанська сієста", "ремонт квартири", "сусіди", "таксист",
    "авіапереліт", "готель", "банк", "податкова", "космос", "динозаври", "собака",
    "папуга", "бджоли", "бізнес-план", "стартап", "дієта", "спортзал", "весілля",
    "діти та батьки", "хімія", "фізика", "історики", "археологи", "музей", "оркестр",
    "шахи", "кава", "понеділок", "відпустка", "Excel", "наради в Zoom",
]
FACT_THEMES = [
    "тварини", "космос", "їжа та її історія", "мови й слова", "медицина",
    "кров і імунітет", "географія", "фізика", "хімія", "історія торгівлі",
    "мореплавство", "винаходи", "архітектура", "математика", "рослини",
    "океан", "людський мозок", "музика", "давній світ", "погода і клімат",
]
MOTIVATION_ANGLES = [
    "стоїчний — у дусі Сенеки чи Марка Аврелія, але своїми словами і з сучасним образом",
    "смішний — абсурдний поворот, після якого хочеться посміхнутись і піти робити справи",
    "дивовижний — через реальний вражаючий факт з природи, космосу чи історії",
    "бенгер — коротко й різко, як удар у гонг, до 12 слів",
    "тонка самоіронія ділової людини",
    "порада старого капітана, який бачив усі шторми",
    "інструкція з техніки безпеки для амбітних",
    "репліка спортивного коментатора в кульмінацію матчу",
    "метафора з кухні, вина або кави",
    "філософський парадокс, що перевертає звичну думку",
    "прогноз погоди, але для справ на сьогодні",
    "що сказала б тварина — восьминіг, ворона, бобер чи мураха",
    "через реальний історичний епізод і несподіваний висновок",
    "фраза, яку хочеться написати маркером на дошці в переговорній",
]
BANNED_JOKE_MARKERS = [
    "scarecrow", "outstanding in his field", "опудал", "make up everything", "impasta",
    "two tired", "two-tired", "anti-gravity", "антигравітац", "fsh", "nacho cheese",
    "dino-snore", "meowtain", "waist of time", "pouch potato", "salad dressing",
    "no atmosphere", "abdominal snowman", "don't know y", "eyebrows too high",
    "skeleton", "скелет", "pork chop", "got mugged", "enough dough", "boomerang",
    "orange and sounds like a parrot", "invisible man",
]
BANNED_MOTIVATION = [
    "кожен день — новий шанс", "вір у себе", "ти все зможеш", "не здавайся",
    "крок за кроком", "найкращий час", "рухайся вперед", "твій потенціал",
]


# ── Допоміжні ─────────────────────────────────────────────────────────────────
def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(s).lower())).strip()


def clean_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def esc(s):
    return html.escape(str(s).strip(), quote=False)


def tg_len(s):
    """Довжина видимого тексту так, як її рахує Telegram (UTF-16)."""
    visible = html.unescape(re.sub(r"<[^>]+>", "", s))
    return len(visible.encode("utf-16-le")) // 2


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── Погода і ринки ────────────────────────────────────────────────────────────
def weather_icon(code):
    if code == 0:
        return "☀️"
    if code in (1, 2):
        return "⛅"
    if code == 3:
        return "☁️"
    if code in (45, 48):
        return "🌫️"
    if 51 <= code <= 67:
        return "🌧️"
    if 71 <= code <= 77 or code in (85, 86):
        return "❄️"
    if 80 <= code <= 82:
        return "🌦️"
    if code >= 95:
        return "⛈️"
    return "🌡️"


def get_weather(lat, lon, city):
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weathercode",
                    "daily": "temperature_2m_max", "forecast_days": 1, "timezone": "auto"},
            timeout=10,
        )
        d = r.json()
        temp = round(d["current"]["temperature_2m"])
        tmax = round(d["daily"]["temperature_2m_max"][0])
        return f"{city}: {temp}°C {weather_icon(d['current']['weathercode'])} (вдень до {tmax}°)"
    except Exception as e:
        print(f"⚠️ Погода {city}: {e}")
        return f"{city}: недоступно"


def get_stock(ticker, label, currency):
    if yf is None:
        return f"{label}: н/д"
    try:
        close = yf.Ticker(ticker).history(period="5d")["Close"].dropna()
        if close.empty:
            return f"{label}: н/д"
        price = close.iloc[-1]
        prev = close.iloc[-2] if len(close) >= 2 else price
        pct = (price - prev) / prev * 100 if prev else 0
        arrow = "📈" if pct >= 0 else "📉"
        return f"{label}: {price:.2f} {currency} ({'+' if pct >= 0 else ''}{pct:.2f}%) {arrow}"
    except Exception as e:
        print(f"⚠️ Акції {label}: {e}")
        return f"{label}: н/д"


# ── RSS ───────────────────────────────────────────────────────────────────────
def collect_articles(now_utc):
    articles, seen = [], set()
    for source, feeds in SOURCES.items():
        buckets = []
        for feed in feeds:
            cat, url = feed[0], feed[1]
            link_filter = feed[2] if len(feed) > 2 else None
            items = []
            try:
                r = requests.get(url, headers=HTTP_HEADERS, timeout=15)
                r.raise_for_status()
                for e in feedparser.parse(r.content).entries[:20]:
                    link = (e.get("link") or "").strip()
                    title = clean_text(e.get("title"))
                    if not link or not title:
                        continue
                    if link_filter and not re.search(link_filter, link):
                        continue
                    key = link.split("?")[0].rstrip("/")
                    if key in seen:
                        continue
                    pp = e.get("published_parsed") or e.get("updated_parsed")
                    if pp and now_utc - datetime(*pp[:6], tzinfo=timezone.utc) > FRESH_OVERRIDE.get(source, FRESH):
                        continue
                    seen.add(key)
                    items.append({"source": source, "cat": cat, "title": title, "link": link,
                                  "summary": clean_text(e.get("summary"))[:240]})
                if not items:
                    print(f"⚠️ RSS {source} [{cat}]: HTTP {r.status_code}, записів у стрічці {len(feedparser.parse(r.content).entries)}, свіжих 0")
            except Exception as ex:
                print(f"⚠️ RSS {source} [{cat}]: {ex}")
            buckets.append(items)
        picked = []                      # по черзі з кожної рубрики, щоб спорт не з'їв усе
        while len(picked) < PER_SOURCE and any(buckets):
            for b in buckets:
                if b and len(picked) < PER_SOURCE:
                    picked.append(b.pop(0))
        print(f"📰 {source}: {len(picked)} статей")
        articles.extend(picked)
    for i, a in enumerate(articles, 1):
        a["id"] = i
    return articles


# ── Gemini ────────────────────────────────────────────────────────────────────
def build_prompt(articles, hist, joke_format, joke_topic, fact_theme, angle):
    arts = "\n".join(f"[{a['id']}] {a['source']} | {a['cat']} | {a['title']}\n     {a['summary']}"
                     for a in articles)
    jokes = "\n".join(f"- {j}" for j in hist["jokes"]) or "немає"
    facts = "; ".join(hist["facts"][-40:]) or "немає"
    motiv = "\n".join(f"- {m}" for m in hist["motivations"][-20:]) or "немає"
    numbers = "; ".join(hist["numbers"][-15:]) or "немає"
    return f"""Ти — редактор ранкового дайджесту для українського бізнесмена (фарма, експорт, геополітика, економіка, технології, наука, культура). Пишеш українською: живо, стисло, з цифрами, без води і канцеляриту. Без markdown.

Нижче {len(articles)} свіжих статей з провідних видань. У кожної є номер [id].

{arts}

Поверни ТІЛЬКИ JSON такої структури:
{{
  "top":     [{{"id": 1, "emoji": "🌍", "text": "..."}}],
  "sport":   [{{"id": 1, "emoji": "⚽", "text": "..."}}],
  "culture": [{{"id": 1, "emoji": "🎭", "text": "..."}}],
  "crazy":   [{{"id": 1, "emoji": "🤪", "text": "..."}}],
  "number":  {{"id": 1, "value": "...", "text": "..."}},
  "fact": "...",
  "fact_topic": "...",
  "joke": "...",
  "joke_key": "...",
  "motivation": "..."
}}

НОВИНИ
• top — 8 кандидатів у порядку важливості: геополітика, світова економіка, бізнес, технології/AI, фарма і медицина. Різні теми, жодних дублів однієї події. Бери з різних видань, не більше 2 з одного — що ширша палітра джерел, то краще.
• sport — 3 кандидати, culture — 3 кандидати (культура, мистецтво, кіно, книги, наукове відкриття), crazy — 3 кандидати: найдивніша, найкумедніша або найшаленіша новина дня.
• text — 1–2 речення українською: суть і цифри, якщо є. Якщо є влучний наслідок чи цікаве трактування — додай коротко; якщо немає — нічого не вигадуй. Не згадуй назву видання в тексті.
• emoji — одне, за темою. id — тільки номери зі списку вище.

ЦИФРА ДНЯ
• Одна вражаюча або показова цифра зі статистики в СЬОГОДНІШНІХ статтях вище (із заголовка чи опису — не вигадуй і не бери з пам'яті). Бажано зі статті, якої немає серед новин.
• value — сама цифра з одиницями ("$2,1 трлн", "47%", "1 з 5"); text — одне речення, що вона означає і чому це цікаво; id — стаття-джерело.
• Не повторюй нещодавні: {numbers}

ФАКТ ДНЯ
• 2–3 речення: перевірений науковий, історичний або дивовижний факт. Тема сьогодні: {fact_theme}.
• fact_topic — тема факту у 3–6 словах. Не повторюй уже використані теми: {facts}

ЖАРТ ДНЯ
• Замовлення на сьогодні: формат — {joke_format}; тема — {joke_topic}.
• Від 1 до 10 речень. Гра слів не обов'язкова: годяться анекдоти, діалоги, міні-історії, спостереження.
• Мова: якщо жарт за походженням англійський — залиш англійською; український — українською. Каламбури не перекладай.
• Заборонено: заїжджені dad jokes з топ-списків інтернету (опудало «outstanding in his field», атоми, що «make up everything», скелети, impasta, two-tired тощо) і все, що вже було (список нижче). Якщо першим спадає на думку відомий жарт — відкинь і шукай далі.
• joke_key — суть жарту у 5–10 словах українською.
Вже були:
{jokes}

МОТИВАЦІЯ НА ДЕНЬ
• Рівно одне речення, до 30 слів. Кут сьогодні: {angle}.
• Це найважливіше: жодних шаблонів і банальностей. Без цитат відомих людей, без фраз на кшталт «кожен день — новий шанс», «вір у себе», «не здавайся», «крок за кроком», «найкращий час — зараз», «твій потенціал». Не починай зі звертання.
• Має бути свіже, конкретне, з образом або несподіваним поворотом — щоб хотілося переслати другу.
• Не схоже на попередні:
{motiv}
"""


def make_client():
    from google import genai
    from google.genai import types
    # v1beta обов'язково: у v1 немає JSON-режиму і моделей *-latest (нові версії бібліотеки за замовчуванням беруть v1)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(api_version="v1beta", timeout=120_000))
    config = types.GenerateContentConfig(response_mime_type="application/json")
    return client, config


def parse_json(txt):
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (txt or "").strip())
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0) if m else txt)


def ask_gemini(client, config, prompt, required):
    for model in MODELS:
        for attempt in range(1, 3):
            try:
                # друга спроба — без JSON-режиму (промпт і так просить JSON, parse_json його витягне)
                cfg = config if attempt == 1 else None
                resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
                data = parse_json(resp.text)
                if all(data.get(k) for k in required):
                    print(f"✅ Gemini: {model}")
                    return data
                print(f"⚠️ {model} спроба {attempt}: неповна відповідь")
            except Exception as e:
                print(f"❌ {model} спроба {attempt}: {str(e)[:300]}")
            time.sleep(8)
    return None


def joke_is_repeat(joke, key, jokes_used):
    j = norm(joke)
    if any(m in j for m in BANNED_JOKE_MARKERS):
        return True
    head, k = norm(joke[:60]), norm(key)
    for old in jokes_used:
        old_key, _, old_head = old.partition(" | ")
        if not old_head:                              # старий формат: лише перші 60 символів
            old_head, old_key = old_key, ""
        if difflib.SequenceMatcher(None, head, norm(old_head)).ratio() > 0.72:
            return True
        if k and old_key and difflib.SequenceMatcher(None, k, norm(old_key)).ratio() > 0.8:
            return True
    return False


# ── Збірка повідомлення ───────────────────────────────────────────────────────
def to_id(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def select_news(data, by_id):
    counts, taken = Counter(), set()

    def choose(cands, n, cap):
        out = []
        for c in cands or []:
            if len(out) >= n:
                break
            if not isinstance(c, dict):
                continue
            i = to_id(c.get("id"))
            a = by_id.get(i)
            if not a or i in taken or not str(c.get("text", "")).strip():
                continue
            if counts[a["source"]] >= cap:
                continue
            out.append({**c, "id": i})
            taken.add(i)
            counts[a["source"]] += 1
        return out

    top = choose(data.get("top"), 5, 2)
    if len(top) < 5:
        top += choose(data.get("top"), 5 - len(top), MAX_PER_OUTLET)
    extra = []
    for key in ("sport", "culture", "crazy"):
        extra += choose(data.get(key), 1, MAX_PER_OUTLET)
    print("📊 Видання в дайджесті:", dict(counts))
    return top + extra, taken


def source_link(a):
    return f'<a href="{html.escape(a["link"], quote=True)}">{esc(a["source"])}</a>'


def news_line(item, by_id):
    a = by_id[item["id"]]
    emoji = str(item.get("emoji") or "•").strip()[:4]
    return f"{esc(emoji)} {source_link(a)}: {esc(item['text'])}"


def build_blocks(ctx, data, by_id):
    blocks = [f"Добрий ранок, {esc(ctx['greeting'])}!\n{esc(ctx['date_line'])}",
              "━━━ ПОГОДА ━━━\n" + "\n".join(esc(w) for w in ctx["weather"])]
    news, taken = select_news(data, by_id)
    if news:
        blocks.append("━━━ НОВИНИ ━━━\n" + "\n\n".join(news_line(n, by_id) for n in news))
    blocks.append("━━━ РИНКИ 💹 ━━━\n" + "\n".join(esc(s) for s in ctx["stocks"]))

    num = data.get("number") or {}
    if isinstance(num, dict) and num.get("value") and num.get("text"):
        a = by_id.get(to_id(num.get("id")))
        src = f" ({source_link(a)})" if a else ""
        blocks.append(f"━━━ ЦИФРА ДНЯ 🔢 ━━━\n<b>{esc(num['value'])}</b> — {esc(num['text'])}{src}")
    if data.get("fact"):
        blocks.append("━━━ ФАКТ ДНЯ 🧠 ━━━\n" + esc(data["fact"]))
    if data.get("joke"):
        blocks.append("━━━ ЖАРТ ДНЯ 😄 ━━━\n" + esc(data["joke"]))
    if data.get("motivation"):
        blocks.append("━━━━━━━━━━━━━━\n⚡ " + esc(data["motivation"]))
    return blocks


def build_fallback_blocks(ctx, articles):
    """Якщо Gemini не відповів — хоча б заголовки з різних видань, без обробки."""
    blocks = [f"Добрий ранок, {esc(ctx['greeting'])}!\n{esc(ctx['date_line'])}",
              "━━━ ПОГОДА ━━━\n" + "\n".join(esc(w) for w in ctx["weather"])]
    if articles:
        lines, per = [], Counter()
        for a in articles:
            if a["cat"] != "спорт" and per[a["source"]] < 2 and len(lines) < 8:
                lines.append(f"• {source_link(a)}: {esc(a['title'])}")
                per[a["source"]] += 1
        blocks.append("━━━ ЗАГОЛОВКИ ━━━\n🤖 Gemini сьогодні не вийшов на зв'язок, тому без перекладу:\n\n"
                      + "\n".join(lines))
    else:
        blocks.append("⚠️ Сьогодні не вдалося зібрати новини.")
    blocks.append("━━━ РИНКИ 💹 ━━━\n" + "\n".join(esc(s) for s in ctx["stocks"]))
    return blocks


def split_messages(blocks, limit=3900):
    msgs, cur = [], ""
    for b in blocks:
        cand = f"{cur}\n\n{b}" if cur else b
        if tg_len(cand) <= limit:
            cur = cand
            continue
        if cur:
            msgs.append(cur)
        cur = b
        while tg_len(cur) > limit:               # дуже довгий блок — ріжемо по рядках
            lines, part = cur.split("\n"), ""
            while lines and tg_len(f"{part}\n{lines[0]}" if part else lines[0]) <= limit:
                part = f"{part}\n{lines.pop(0)}" if part else lines.pop(0)
            if not part:                         # один рядок довший за ліміт
                part = lines.pop(0)
            msgs.append(part)
            cur = "\n".join(lines)
    if cur:
        msgs.append(cur)
    return msgs


# ── Telegram ──────────────────────────────────────────────────────────────────
def tg_send(chat_id, text):
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "link_preview_options": {"is_disabled": True}}
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.ok:
                return True
            print(f"⚠️ Telegram {chat_id}: {r.status_code} {r.text[:200]}")
            if r.status_code == 400 and "entit" in r.text.lower():
                payload = {"chat_id": chat_id, "text": html.unescape(re.sub(r"<[^>]+>", "", text)),
                           "link_preview_options": {"is_disabled": True}}
                continue
            if r.status_code == 403:             # користувач заблокував бота
                return False
            time.sleep(r.json().get("parameters", {}).get("retry_after", 3) if r.status_code == 429 else 3)
        except Exception as e:
            print(f"⚠️ Telegram {chat_id}: {e}")
            time.sleep(3)
    return False


# ── Збереження історії ────────────────────────────────────────────────────────
def save_and_push(used, date_str):
    with open(USED_FILE, "w", encoding="utf-8") as f:
        json.dump(used, f, ensure_ascii=False, indent=2)
    try:
        run = lambda *c: subprocess.run(list(c), check=True)
        run("git", "config", "user.email", "digest-bot@github-actions")
        run("git", "config", "user.name", "Digest Bot")
        run("git", "add", USED_FILE)
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
            run("git", "commit", "-m", f"chore: update used.json [{date_str}]")
            subprocess.run(["git", "pull", "--rebase", "--quiet"])
            run("git", "push")
            print("✅ used.json збережено в репозиторій")
    except Exception as e:
        print(f"⚠️ Не вдалося запушити used.json: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    mode = (os.environ.get("MODE") or "normal").strip().lower()
    test = mode == "test"
    now_kyiv = datetime.now(KYIV)
    today = now_kyiv.date().isoformat()
    date_str = f"{now_kyiv.day} {MONTHS[now_kyiv.month - 1]} {now_kyiv.year}"
    print(f"Режим: {mode} | {now_kyiv:%Y-%m-%d %H:%M} Київ")

    used = load_json(USED_FILE, {})
    if not test and used.get("last_sent") == today:
        print(f"ℹ️ Дайджест за {today} вже надіслано — нічого не роблю.")
        return

    subscribers = [str(x) for x in load_json("subscribers.json", {}).get("subscribers", [])]
    recipients = subscribers[:1] if test else subscribers
    hist = {k: list(used.get(k, []))[-n:] for k, n in HISTORY_LIMITS.items()}

    ctx = {
        "greeting": get_greeting(now_kyiv),
        "date_line": f"{WEEKDAYS[now_kyiv.weekday()]}, {date_str}",
        "weather": [get_weather(50.4501, 30.5234, "Київ"), get_weather(41.3851, 2.1734, "Барселона")],
        "stocks": [get_stock("CSL.AX", "CSL", "AUD"), get_stock("GRF.MC", "Grifols", "EUR"),
                   get_stock("TAK", "Takeda", "USD")],
    }
    articles = collect_articles(datetime.now(timezone.utc))
    by_id = {a["id"]: a for a in articles}
    print(f"Всього статей: {len(articles)}")

    data = None
    if articles:
        rnd = random.SystemRandom()
        client, config = make_client()
        prompt = build_prompt(articles, hist, rnd.choice(JOKE_FORMATS), rnd.choice(JOKE_TOPICS),
                              rnd.choice(FACT_THEMES), rnd.choice(MOTIVATION_ANGLES))
        data = ask_gemini(client, config, prompt, required=("top",))

        # Жарт-повтор → окремо просимо новий (до 2 разів), інакше рубрику пропускаємо
        if data and data.get("joke"):
            tries = 0
            while joke_is_repeat(data["joke"], data.get("joke_key", ""), hist["jokes"]) and tries < 2:
                tries += 1
                print(f"🔁 Жарт схожий на старий, перегенеровую ({tries}): {data['joke'][:60]}")
                jp = (f"Придумай один жарт: формат — {rnd.choice(JOKE_FORMATS)}; тема — {rnd.choice(JOKE_TOPICS)}. "
                      "1–10 речень. Англійський за походженням — англійською, український — українською. "
                      "Жодних відомих dad jokes з інтернет-топів. Не схожий на ці:\n"
                      + "\n".join(f"- {j}" for j in hist["jokes"] + [data["joke"][:60]])
                      + '\nПоверни ТІЛЬКИ JSON: {"joke": "...", "joke_key": "суть у 5–10 словах"}')
                new = ask_gemini(client, config, jp, required=("joke",))
                if new:
                    data["joke"], data["joke_key"] = new["joke"], new.get("joke_key", "")
            if joke_is_repeat(data["joke"], data.get("joke_key", ""), hist["jokes"]):
                print("⚠️ Свіжого жарту не вийшло — рубрику пропускаю")
                data["joke"] = None

        if data and any(m in norm(data.get("motivation", "")) for m in map(norm, BANNED_MOTIVATION)):
            print(f"⚠️ Мотивація шаблонна, прибираю: {data['motivation']}")
            data["motivation"] = None

    blocks = build_blocks(ctx, data, by_id) if data else build_fallback_blocks(ctx, articles)
    messages = split_messages(blocks)
    print("\n" + "\n\n".join(messages) + "\n")

    sent = 0
    for cid in recipients:
        ok = all([tg_send(cid, m) for m in messages])
        sent += ok
        print(f"Telegram {cid}: {'✅' if ok else '❌'}")
        time.sleep(0.5)
    print(f"Надіслано {sent}/{len(recipients)}")

    if test:
        print("🧪 Тестовий режим — історію не зберігаю.")
        return
    if not sent:
        sys.exit("❌ Нікому не вдалося надіслати")

    used = {"last_sent": today, **hist}
    if data:
        if data.get("joke"):
            used["jokes"].append(f"{str(data.get('joke_key', '')).strip()} | {data['joke'][:60]}")
        if data.get("fact_topic") or data.get("fact"):
            used["facts"].append(str(data.get("fact_topic") or data["fact"][:60]).strip())
        if data.get("motivation"):
            used["motivations"].append(str(data["motivation"]).strip())
        num = data.get("number") or {}
        if isinstance(num, dict) and num.get("value"):
            used["numbers"].append(f"{num['value']} — {str(num.get('text', ''))[:60]}")
    for k, n in HISTORY_LIMITS.items():
        used[k] = used[k][-n:]
    save_and_push(used, date_str)


if __name__ == "__main__":
    main()
