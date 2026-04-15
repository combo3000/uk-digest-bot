import requests
import json
import os
import subprocess

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Читаємо поточних підписників
with open("subscribers.json", "r") as f:
    subscribers = json.load(f)

# Перевіряємо нові повідомлення боту
resp = requests.get(
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
    params={"timeout": 5},
)
data = resp.json()

new_users = False
for update in data.get("result", []):
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")
    first_name = msg.get("chat", {}).get("first_name", "")

    if chat_id and chat_id not in subscribers:
        subscribers.append(chat_id)
        new_users = True
        print(f"Новий підписник: {first_name} ({chat_id})")

        # Привітання новому підписнику
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"Привіт, {first_name}! 🇬🇧\nТепер щоранку о ~9:30 ти отримуватимеш дайджест цікавих новин з британських ЗМІ українською.\n\nБот зроблений Тарасом за допомогою AI.",
            },
        )

# Зберігаємо оновлений список
if new_users:
    with open("subscribers.json", "w") as f:
        json.dump(subscribers, f)

    # Комітимо зміни в GitHub
    subprocess.run(["git", "config", "user.name", "bot"], check=True)
    subprocess.run(["git", "config", "user.email", "bot@bot.com"], check=True)
    subprocess.run(["git", "add", "subscribers.json"], check=True)
    subprocess.run(["git", "commit", "-m", "update subscribers"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(f"Збережено {len(subscribers)} підписників")
else:
    print("Нових підписників немає")
