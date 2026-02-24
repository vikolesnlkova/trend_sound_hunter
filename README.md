# 🎯 Trend & Sound Hunter Bot

Бот запускается бесплатно на **GitHub Actions** каждый день в 09:00 МСК.
Читает треки из твоей Google Sheets, находит тренды Reels/TikTok, отправляет рецепты в Telegram.

---

## 📋 Что нужно сделать (один раз)

### Шаг 1 — Создай GitHub репозиторий

1. Зайди на [github.com](https://github.com) → **New repository**
2. Название: `trend-sound-hunter` (любое)
3. Тип: **Private** (чтобы секреты не светились)
4. Нажми **Create repository**
5. Загрузи два файла в корень репо: `bot.py` и папку `.github/workflows/daily_digest.yml`

---

### Шаг 2 — Узнай свой Telegram Chat ID

1. Найди в Telegram бот **@userinfobot**
2. Нажми Start — он пришлёт твой ID (число вида `123456789`)
3. Запиши его, понадобится в Шаге 5

---

### Шаг 3 — Получи Anthropic API Key

1. Зайди на [console.anthropic.com](https://console.anthropic.com)
2. **API Keys** → **Create Key**
3. Скопируй ключ (начинается с `sk-ant-...`)

---

### Шаг 4 — Создай Google Service Account и дай доступ к таблице

Это самый важный шаг для доступа к закрытой Google Sheets.

#### 4а. Создай сервисный аккаунт:
1. Зайди на [console.cloud.google.com](https://console.cloud.google.com)
2. Создай новый проект (или выбери существующий) — кнопка вверху слева
3. В поиске найди **"Google Sheets API"** → нажми **Enable**
4. Левое меню → **IAM & Admin** → **Service Accounts**
5. Нажми **+ Create Service Account**
   - Имя: `trend-hunter`
   - Нажми **Create and Continue** → **Done**
6. Кликни на созданный аккаунт → вкладка **Keys**
7. **Add Key** → **Create new key** → **JSON** → **Create**
8. Скачается файл `.json` — открой его в текстовом редакторе

#### 4б. Дай сервисному аккаунту доступ к таблице:
1. В скачанном JSON найди поле `"client_email"` — скопируй этот email
   (выглядит как `trend-hunter@your-project.iam.gserviceaccount.com`)
2. Открой свою Google Sheets таблицу
3. Нажми **Поделиться** (Share) → вставь этот email → роль **Viewer** → **Send**

#### 4в. Закодируй JSON в base64:
На Mac/Linux в терминале:
```bash
base64 -i path/to/your-key-file.json | tr -d '\n'
```
На Windows (PowerShell):
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("path\to\your-key-file.json"))
```
Скопируй результат — это и есть значение для секрета `GOOGLE_SA_JSON`.

---

### Шаг 5 — Добавь секреты в GitHub

1. В твоём репозитории: **Settings** → **Secrets and variables** → **Actions**
2. Нажми **New repository secret** и добавь 4 секрета:

| Название секрета | Значение |
|-----------------|----------|
| `TELEGRAM_TOKEN` | `8243538711:AAED6X7WuAKYuyHEA7PoRRyjOw2d59xikQE` |
| `TELEGRAM_CHAT_ID` | твой ID из Шага 2 (например `123456789`) |
| `ANTHROPIC_API_KEY` | ключ из Шага 3 (начинается с `sk-ant-`) |
| `GOOGLE_SA_JSON` | base64-строка из Шага 4в |

---

### Шаг 6 — Тестовый запуск

1. В репозитории: вкладка **Actions**
2. Слева выбери **Trend & Sound Hunter — Daily Digest**
3. Нажми **Run workflow** → **Run workflow**
4. Смотри логи — через 1–2 минуты придёт сообщение в Telegram!

---

## ⏰ Расписание

По умолчанию бот запускается каждый день в **09:00 МСК** (06:00 UTC).

Чтобы изменить время — отредактируй строку в `.github/workflows/daily_digest.yml`:
```yaml
- cron: "0 6 * * *"   # минуты часы * * *  (UTC)
```
Примеры:
- `0 7 * * *` — 10:00 МСК
- `0 17 * * *` — 20:00 МСК
- `0 6 * * 1-5` — только по будням в 09:00 МСК

---

## 🐞 Частые проблемы

**Ошибка `PERMISSION_DENIED` от Google Sheets**
→ Убедись что добавил email сервисного аккаунта в доступ к таблице (Шаг 4б)

**Ошибка `401` от Anthropic**
→ Проверь секрет `ANTHROPIC_API_KEY` — он должен начинаться с `sk-ant-`

**Сообщение не приходит в Telegram**
→ Проверь `TELEGRAM_CHAT_ID` — должно быть числом без лишних символов

**Workflow не запускается по расписанию**
→ GitHub иногда задерживает cron до 15 мин, это нормально.
→ Если не запускался несколько дней — зайди в Actions и нажми Run workflow вручную

---

## 📊 Структура Google Sheets

Бот понимает любые названия колонок и передаёт все данные в AI.
Рекомендуемые колонки для лучших рецептов:

| Колонка | Пример |
|---------|--------|
| Название | Зелёное небо |
| Жанр/Настроение | Инди-поп, мечтательный |
| Темп/BPM | медленный / 85 BPM |
| О чём | о побеге от городской суеты |
| Инструменты | акустическая гитара, синтезатор |
| Хук/Припев | "и я лечу над городом одна" |
