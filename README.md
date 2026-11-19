# Morning Digest Bot

Щоранковий дайджест у Telegram: погода, 5 головних новин (Economist, NYT, FT, Guardian, BBC, Der Spiegel, Le Monde, Wired, Nature, The Atlantic, El País) + спорт, культура, шалена новина, ринки, цифра дня, факт дня, жарт дня (по черзі з `jokes_queue.json` — 579 перемішаних жартів з Bored Panda і TODAY англійською; коли черга скінчиться — свіжі з boredpanda.com, а якщо сайт недоступний — від Gemini) і картинка дня з Wikimedia Commons (фото з підписом українською). Після генерації українські тексти проходять окрему коректуру (Gemini-коректор виправляє описки й кальки). Погода — Open-Meteo з повторами, запасне джерело — wttr.in.

## Як запускається
- **Основний запуск:** cron-job.org щодня о 08:00 (Europe/Kyiv) робить POST на
  `https://api.github.com/repos/combo3000/uk-digest-bot/actions/workflows/digest.yml/dispatches`
  з тілом `{"ref":"main"}` і заголовками `Authorization: Bearer <fine-grained token, Actions: read & write>`,
  `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`.
- **Резерв:** `schedule` у `digest.yml`. Якщо дайджест за сьогодні вже пішов (`last_sent` у `used.json`), резервний запуск нічого не робить.
- **Тест:** Actions → Morning Digest → Run workflow → mode `test`: дайджест піде тільки першому підписнику, історія не зберігається — крім жарту: тестовий жарт вважається використаним, щоб наступного ранку не повторився.

## Файли
- `send_digest.py` — збір RSS, Gemini, збірка повідомлення, відправка.
- `subscribers.json` — chat_id підписників (перший — адмін, йому йдуть тести).
- `jokes_queue.json` — черга жартів дня; щоб додати жарти, допишіть їх у кінець списку.
- `used.json` — історія жартів (`joke_queue_pos` — номер наступного жарту з черги, `bp_jokes` — id уже надісланих жартів з Bored Panda), фактів і цифр, щоб не повторюватись; `last_sent` — дата останньої відправки.
