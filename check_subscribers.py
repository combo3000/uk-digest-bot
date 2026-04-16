import requests
import json
import os
import subprocess

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

with open("subscribers.json", "r") as f:
    data = json.load(f)

subscribers = data.get("subscribers", [])
last_update_id = data.get("last_update_id", 0)

# Отримуємо тільки нові повідомлення
resp = requests.get(
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
    params={"offset": last_update_id + 1, "timeout": 5},
)
updates = resp.json().get("result", [])

changed = False
for update in updates:
    last_update_id = update["update_id"]
    changed = True
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    first_name = msg.get("chat", {}).get("first_name", "друже")
    text = msg.get("text", "")

    if not chat_id:
        continue

    if chat_id not in subscribers:
        # Новий підписник
        subscribers.append(chat_id)
        print(f"+ Новий підписник: {first_name} ({chat_id})")
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": (
                    f"Привіт, {first_name}! 🇬🇧\n"
                    "Ти підписаний на щоранковий дайджест цікавих новин "
                    "з британських ЗМІ українською.\n"
                    "Чекай дайджест щодня о ~9:30 ранку.\n\n"
                    "Бот зроблений Тарасом за допомогою AI."
                ),
            },
        )
    else:
        # Вже підписаний — просто відповісти
        if text == "/start":
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"Ти вже підписаний, {first_name}! Дайджест надходить щодня о ~9:30 🇬🇧",
                },
            )

# Зберігаємо оновлений стан
with open("subscribers.json", "w") as f:
    json.dump({"subscribers": subscribers, "last_update_id": last_update_id}, f)

if changed:
    subprocess.run(["git", "config", "user.name", "digest-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "bot@digest.com"], check=True)
    subprocess.run(["git", "add", "subscribers.json"], check=True)
    subprocess.run(["git", "commit", "-m", f"subscribers: {len(subscribers)}"], check=True)
    subprocess.run(["git", "push"], check=True)

print(f"Підписників: {len(subscribers)}, last_update_id: {last_update_id}")
