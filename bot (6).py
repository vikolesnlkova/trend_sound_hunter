#!/usr/bin/env python3
"""
Trend & Sound Hunter Bot — Настя Арека
GitHub Actions edition: Google Sheets API + Claude API + Telegram
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ─── КОНФИГУРАЦИЯ (все значения берутся из GitHub Secrets) ───────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_SA_JSON   = os.environ["GOOGLE_SA_JSON"]   # JSON сервисного аккаунта (base64)
SHEET_ID         = "1Q3mi9RB2or2aDbQkb9gu87IgcNVVk-5xsFgaLw0zodU"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── GOOGLE AUTH (без сторонних библиотек) ───────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_jwt(sa: dict) -> str:
    """Создать JWT для Google OAuth2 (RS256) без внешних зависимостей."""
    import struct, hashlib
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets.readonly",
        "aud": "https://oauth2.googleapis.com/token",
        "exp": now + 3600,
        "iat": now,
    }).encode())

    signing_input = f"{header}.{payload}".encode()

    private_key = serialization.load_pem_private_key(
        sa["private_key"].encode(), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def get_google_token() -> str:
    """Получить OAuth2 access token через JWT сервисного аккаунта."""
    raw = base64.b64decode(GOOGLE_SA_JSON).decode()
    sa = json.loads(raw)

    jwt = _make_jwt(sa)
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    return result["access_token"]

# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────

def fetch_tracks(token: str) -> list[dict]:
    """Читать все строки из первого листа таблицы."""
    log.info("Загружаю треки из Google Sheets...")
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"/values/A1:Z200?majorDimension=ROWS"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    rows = data.get("values", [])
    if not rows:
        return []

    headers = [h.strip() for h in rows[0]]
    tracks = []
    for row in rows[1:]:
        # Дополняем строку до длины заголовков
        padded = row + [""] * (len(headers) - len(row))
        entry = {headers[i]: padded[i].strip() for i in range(len(headers))}
        if any(v for v in entry.values()):
            tracks.append(entry)

    log.info(f"Загружено треков: {len(tracks)}")
    return tracks

# ─── CLAUDE API ───────────────────────────────────────────────────────────────

def _http_post(url: str, payload: dict, headers: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def claude(messages: list, max_tokens: int = 2000, use_search: bool = False) -> str:
    """Запрос к Claude с опциональным web_search."""
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if use_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    result = _http_post(
        "https://api.anthropic.com/v1/messages",
        payload,
        {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        }
    )
    return "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")


def find_trends_and_recipes(tracks: list[dict]) -> tuple[str, str]:
    """Один запрос — тренды + рецепты. Экономим токены и избегаем rate limit."""
    log.info("Генерирую тренды и рецепты одним запросом...")
    moscow = datetime.now(timezone(timedelta(hours=3)))
    today = moscow.strftime("%d %B %Y")

    tracks_text = ""
    for i, t in enumerate(tracks[:3], 1):
        vals = list(t.values())[:3]
        tracks_text += f"{i}. {' | '.join(v for v in vals if v)}\n"

    prompt = f"""Сегодня {today}. Ты — Trend & Sound Hunter для певицы Насти Арека (студия Green Touch, travel-блогер, влог из Сеула).

ТРЕКИ НАСТИ:
{tracks_text}

Задача: напиши дайджест в двух частях.

ЧАСТЬ 1 — ТРЕНДЫ (заголовок: "🌍 ТРЕНДЫ ДНЯ")
3 актуальных вирусных формата в Instagram Reels и TikTok.
Для каждого: название, что снимают, почему залетает. По 2 предложения.

ЧАСТЬ 2 — РЕЦЕПТЫ (заголовок: "✨ РЕЦЕПТЫ")
2 рецепта: каждый = 1 трек Насти + 1 тренд из части 1.
Для каждого рецепта:
🎬 Сценарий (15-30 сек)
🎵 Как использовать трек
🌿 Эстетика Насти
📍 Хэштеги и время постинга

Пиши по-русски, конкретно и коротко."""

    result = claude([{"role": "user", "content": prompt}], max_tokens=1200)

    # Делим ответ на две части по заголовкам
    if "✨ РЕЦЕПТЫ" in result:
        parts = result.split("✨ РЕЦЕПТЫ", 1)
        trends_part = parts[0].replace("🌍 ТРЕНДЫ ДНЯ", "").strip()
        recipes_part = parts[1].strip()
    else:
        # Если модель не разделила — отдаём всё как рецепты
        trends_part = "Тренды включены в рецепты ниже."
        recipes_part = result.strip()

    return trends_part, recipes_part

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def tg(method: str, data: dict) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def send(text: str) -> None:
    """Отправить сообщение, нарезая на части если нужно."""
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        tg("sendMessage", {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        time.sleep(0.5)

# ─── ФОРМАТИРОВАНИЕ ───────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(trends: str, recipes: str, count: int) -> str:
    moscow = datetime.now(timezone(timedelta(hours=3)))
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][moscow.weekday()]
    date_str = moscow.strftime("%d.%m.%Y")

    return (
        f"🎯 <b>TREND &amp; SOUND HUNTER</b>\n"
        f"📅 {weekday}, {date_str} · {count} треков в базе\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌍 <b>ТРЕНДЫ ДНЯ</b>\n"
        f"Instagram Reels &amp; TikTok\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{escape_html(trends)}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"✨ <b>РЕЦЕПТЫ ПОД ТВОИ ТРЕКИ</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{escape_html(recipes)}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🪐 <i>Настя Арека × Trend &amp; Sound Hunter</i>\n"
        f"🍃 <i>Green Touch vibes · auto-generated</i>"
    )

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 50)
    log.info("Trend & Sound Hunter Bot — старт")

    try:
        # 1. Google auth
        token = get_google_token()

        # 2. Треки из Sheets
        tracks = fetch_tracks(token)
        if not tracks:
            send("⚠️ Треки не найдены в Google Sheets. Проверь таблицу.")
            return

        # 3. Тренды + рецепты — одним запросом
        trends, recipes = find_trends_and_recipes(tracks)

        # 4. Отправляем
        msg = format_message(trends, recipes, len(tracks))
        send(msg)
        log.info("✅ Готово — сообщение отправлено в Telegram")

    except Exception as e:
        log.error(f"Ошибка: {e}", exc_info=True)
        try:
            send(f"❌ <b>Ошибка Trend Hunter:</b>\n<code>{escape_html(str(e)[:300])}</code>")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
