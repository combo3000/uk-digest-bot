import requests
import json
import os
import subprocess

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Читаємо підписників
with open("subscribers.json", "r") as f:
    data = json.load(f)

# Тепер зберігаємо і підписників, і останній update_id
if isinstance(data, list):
    # Старий формат — конвертуємо
    subscribers = data
    last_update_id = 0
else:
    subscribers = data.get("subscribers", [])
    last_update_id = data.get("last_update_id", 0)

# Отримуємо тільки НОВІ повідомлення
resp = requests.get(
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
    params={"offset": last_update_id + 1, "timeout": 5},
)
updates = resp.json().get("result", [])

new_users = False
for update in updates:
    last_update_id = update["update_id"]
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    first_name = msg.get("chat", {}).get("first_name", "друже")

    if chat_id and chat_id not in subscribers:
        subscribers.append(chat_id)
        new_users = True
        print(f"Новий підписник: {first_name} ({chat_id})")

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"Привіт, {first_name}! 🇬🇧\nТепер щоранку о ~9:30 ти отримуватимеш дайджест цікавих новин з британських ЗМІ українською.\n\nБот зроблений Тарасом за допомогою AI.",
            },
        )

# Зберігаємо новий формат
result = {"subscribers": subscribers, "last_update_id": last_update_id}
with open("subscribers.json", "w") as f:
    json.dump(result, f)

if new_users or updates:
    subprocess.run(["git", "config", "user.name", "bot"], check=True)
    subprocess.run(["git", "config", "user.email", "bot@bot.com"], check=True)
    subprocess.run(["git", "add", "subscribers.json"], check=True)
    subprocess.run(["git", "commit", "-m", "update subscribers"], check=True)
    subprocess.run(["git", "push"], check=True)

print(f"Підписників: {len(subscribers)}, last_update_id: {last_update_id}")
