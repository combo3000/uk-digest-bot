# UK Morning Digest Bot

Щоранковий дайджест у Telegram: погода, 5 головних новин (Economist, NYT, FT, Guardian, BBC) + спорт, культура, шалена новина, ринки, цифра дня, факт дня, жарт і мотивація.

## Як запускається
- **Основний запуск:** cron-job.org щодня о 08:00 (Europe/Kyiv) робить POST на
  `https://api.github.com/repos/combo3000/uk-digest-bot/actions/workflows/digest.yml/dispatches`
  з тілом `{"ref":"main"}` і заголовками `Authorization: Bearer <fine-grained token, Actions: read & write>`,
  `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`.
- **Резерв:** `schedule` у `digest.yml`. Якщо дайджест за сьогодні вже пішов (`last_sent` у `used.json`), резервний запуск нічого не робить.
- **Тест:** Actions → UK Morning Digest → Run workflow → mode `test`: дайджест піде тільки першому підписнику, історія не зберігається.

## Файли
- `send_digest.py` — збір RSS, Gemini, збірка повідомлення, відправка.
- `subscribers.json` — chat_id підписників (перший — адмін, йому йдуть тести).
- `used.json` — історія жартів, фактів, цифр і мотивацій, щоб не повторюватись; `last_sent` — дата останньої відправки.
