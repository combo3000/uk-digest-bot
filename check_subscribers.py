import requests
import json
import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

with open("subscribers.json", "r") as f:
    data = json.load(f)

subscribers = data.get("subscribers", [])
last_update_id = data.get("last_update_id", 0)

resp = requests.get(
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
    params={"offset": last_update_id + 1, "timeout": 5},
)
updates = resp.json().get("result", [])

for update in updates:
    last_update_id = update["update_id"]
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    first_name = msg.get("chat", {}).get("first_name", "друже")

    if not chat_id:
        continue

    if chat_id not in subscribers:
        subscribers.append(chat_id)
        print(f"+ Новий: {first_name} ({chat_id})")
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": f"Привіт, {first_name}! 🇬🇧\nТепер щоранку о ~9:30 ти отримуватимеш дайджест новин з британських ЗМІ.\n\nБот зроблений Тарасом."},
        )
    else:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": f"Ти вже підписаний, {first_name}! Дайджест о ~9:30 🇬🇧"},
        )

with open("subscribers.json", "w") as f:
    json.dump({"subscribers": subscribers, "last_update_id": last_update_id}, f)

print(f"Всього підписників: {len(subscribers)}")
