#!/usr/bin/env python3
"""
Trend & Sound Hunter Bot — Настя Арека
GitHub Actions edition: Google Sheets API + Claude API + Telegram
"""

import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_SA_JSON    = os.environ["GOOGLE_SA_JSON"]
SHEET_ID          = "1Q3mi9RB2or2aDbQkb9gu87IgcNVVk-5xsFgaLw0zodU"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── GOOGLE AUTH ──────────────────────────────────────────────────────────────

def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _make_jwt(sa):
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    now = int(time.time())
    h = _b64url(json.dumps({"alg":"RS256","typ":"JWT"}).encode())
    p = _b64url(json.dumps({"iss":sa["client_email"],
        "scope":"https://www.googleapis.com/auth/spreadsheets.readonly",
        "aud":"https://oauth2.googleapis.com/token",
        "exp":now+3600,"iat":now}).encode())
    sig = serialization.load_pem_private_key(
        sa["private_key"].encode(), password=None
    ).sign(f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{h}.{p}.{_b64url(sig)}"

def get_google_token():
    sa  = json.loads(base64.b64decode(GOOGLE_SA_JSON).decode())
    jwt = _make_jwt(sa)
    data = urllib.parse.urlencode({
        "grant_type":"urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":jwt}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data,
        headers={"Content-Type":"application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]

# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────

def fetch_tracks(token):
    log.info("Загружаю треки...")
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
           "/values/A1:Z200?majorDimension=ROWS")
    req = urllib.request.Request(url, headers={"Authorization":f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.loads(r.read()).get("values", [])
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    tracks  = []
    for row in rows[1:]:
        padded = row + [""]*(len(headers)-len(row))
        entry  = {headers[i]: padded[i].strip() for i in range(len(headers))}
        if any(v for v in entry.values()):
            tracks.append(entry)
    log.info(f"Треков: {len(tracks)}")
    return tracks

# ─── CLAUDE ───────────────────────────────────────────────────────────────────

def _post(url, payload, headers):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data,
           headers={"Content-Type":"application/json", **headers})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            # 529 = перегрузка, 529/rate limit — ждём и повторяем
            if e.code in (529, 429) and attempt < 4:
                wait = 30 * (attempt + 1)
                log.warning(f"HTTP {e.code}, жду {wait}с (попытка {attempt+1}/5)...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}") from e
    raise RuntimeError("Все попытки исчерпаны")

def claude(messages, max_tokens=1200, use_search=False):
    payload = {"model":"claude-haiku-4-5-20251001",
               "max_tokens":max_tokens, "messages":messages}
    if use_search:
        payload["tools"] = [{"type":"web_search_20250305","name":"web_search"}]
    result = _post("https://api.anthropic.com/v1/messages", payload,
                   {"x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"})
    return "".join(b.get("text","") for b in result.get("content",[]) if b.get("type")=="text")

# ─── ПОИСК ТРЕНДОВ ────────────────────────────────────────────────────────────

def fetch_trends():
    log.info("Ищу свежие тренды...")
    moscow = datetime.now(timezone(timedelta(hours=3)))
    today  = moscow.strftime("%B %d, %Y")

    raw = claude([{"role":"user","content":
        f"Today is {today}. Use web search to find 3 BRAND NEW emerging TikTok and Instagram Reels "
        f"trends from the LAST 7 DAYS that are just starting to go viral globally (not in Russia). "
        f"For each trend you MUST find one real working video URL example "
        f"(from tiktok.com, instagram.com, or youtube.com/shorts).\n\n"
        f"Reply ONLY in this exact format, nothing else:\n\n"
        f"===TREND1===\n"
        f"NAME: [trend name in Russian]\n"
        f"WHAT: [what people film — 2 sentences in Russian]\n"
        f"AUDIO: [song/sound used]\n"
        f"VIRAL: [why it spreads — 1 sentence in Russian]\n"
        f"URL: [real video link]\n\n"
        f"===TREND2===\n"
        f"NAME: ...\n"
        f"WHAT: ...\n"
        f"AUDIO: ...\n"
        f"VIRAL: ...\n"
        f"URL: ...\n\n"
        f"===TREND3===\n"
        f"NAME: ...\n"
        f"WHAT: ...\n"
        f"AUDIO: ...\n"
        f"VIRAL: ...\n"
        f"URL: ..."
    }], max_tokens=900, use_search=True)
    return raw

# ─── РЕЦЕПТЫ ─────────────────────────────────────────────────────────────────

def make_recipes(tracks, trends_raw):
    log.info("Генерирую рецепты...")
    tracks_text = ""
    for i, t in enumerate(tracks[:4], 1):
        vals = list(t.values())[:4]
        tracks_text += f"{i}. {' | '.join(v for v in vals if v)}\n"

    raw = claude([{"role":"user","content":
        f"Ты создаёшь контент для певицы Насти Арека (студия Green Touch 🍃, travel-блогер, Сеул).\n\n"
        f"ТРЕНДЫ:\n{trends_raw}\n\n"
        f"ТРЕКИ НАСТИ:\n{tracks_text}\n\n"
        f"Напиши РОВНО 2 рецепта. Каждый = 1 трек + 1 тренд.\n"
        f"Используй ТОЛЬКО такой формат, без markdown символов ** # и т.п.:\n\n"
        f"РЕЦЕПТ 1 — [название трека] × [название тренда]\n"
        f"🎬 Сценарий: [что снимать конкретно, 2-3 предложения]\n"
        f"🎵 Трек: [какой момент, тайминг]\n"
        f"🌿 Эстетика: [Green Touch / travel детали]\n"
        f"📍 Теги: #тег1 #тег2 #тег3 #тег4 #тег5 | Постить в [время]\n\n"
        f"РЕЦЕПТ 2 — [название трека] × [название тренда]\n"
        f"🎬 Сценарий: ...\n"
        f"🎵 Трек: ...\n"
        f"🌿 Эстетика: ...\n"
        f"📍 Теги: ... | Постить в ...\n\n"
        f"Только русский язык. Никаких лишних символов."
    }], max_tokens=900, use_search=False)
    return raw

# ─── ПАРСИНГ И ФОРМАТИРОВАНИЕ ─────────────────────────────────────────────────

def parse_trends(raw):
    trends = []
    for block in re.split(r'===TREND\d+===', raw):
        block = block.strip()
        if not block:
            continue
        t = {}
        for line in block.splitlines():
            for key in ["NAME","WHAT","AUDIO","VIRAL","URL"]:
                if line.startswith(f"{key}:"):
                    t[key] = line[len(key)+1:].strip()
        if t.get("NAME"):
            trends.append(t)
    return trends[:3]

def clean(text):
    """Убираем markdown, оставляем чистый текст для Telegram HTML."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'#{1,4} *',      '',    text)
    text = re.sub(r'---+',          '─'*15, text)
    text = text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    return text.strip()

def build_trends_section(trends):
    if not trends:
        return "Не удалось загрузить тренды — попробуй позже."
    parts = []
    for i, t in enumerate(trends, 1):
        name  = clean(t.get("NAME","—"))
        what  = clean(t.get("WHAT",""))
        audio = clean(t.get("AUDIO",""))
        viral = clean(t.get("VIRAL",""))
        url   = t.get("URL","").strip()

        s = f"<b>{i}. {name}</b>\n"
        if what:  s += f"📹 {what}\n"
        if audio: s += f"🎵 <i>{audio}</i>\n"
        if viral: s += f"⚡ {viral}\n"
        if url and url.startswith("http"):
            s += f'🔗 <a href="{url}">Смотреть пример видео →</a>'
        else:
            s += "🔗 ссылка не найдена"
        parts.append(s)
    return "\n\n".join(parts)

def build_recipes_section(raw):
    return clean(raw)

# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def tg_send(text):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=payload, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            json.loads(r.read())
        time.sleep(0.5)

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    log.info("="*50)
    log.info("Trend & Sound Hunter — старт")

    try:
        token  = get_google_token()
        tracks = fetch_tracks(token)
        if not tracks:
            tg_send("⚠️ Треки не найдены в Google Sheets.")
            return

        trends_raw   = fetch_trends()
        recipes_raw  = make_recipes(tracks, trends_raw)

        trends_list  = parse_trends(trends_raw)
        trends_block = build_trends_section(trends_list)
        recipes_block= build_recipes_section(recipes_raw)

        moscow  = datetime.now(timezone(timedelta(hours=3)))
        weekday = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"][moscow.weekday()]
        date    = moscow.strftime("%d.%m.%Y")

        msg = (
            f"🎯 <b>TREND &amp; SOUND HUNTER</b>\n"
            f"📅 {weekday}, {date} · {len(tracks)} треков в базе\n"
            f"━━━━━━━━━━━━━━━━━\n\n"

            f"🌍 <b>СВЕЖИЕ ЗАРУБЕЖНЫЕ ТРЕНДЫ</b>\n"
            f"<i>Только набирают силу · последние 7 дней</i>\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"{trends_block}\n\n"

            f"━━━━━━━━━━━━━━━━━\n"
            f"✨ <b>РЕЦЕПТЫ ПОД ТВОИ ТРЕКИ</b>\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"{recipes_block}\n\n"

            f"━━━━━━━━━━━━━━━━━\n"
            f"🪐 <i>Настя Арека × Trend &amp; Sound Hunter</i> 🍃"
        )

        tg_send(msg)
        log.info("✅ Отправлено!")

    except Exception as e:
        log.error(f"Ошибка: {e}", exc_info=True)
        err = str(e)[:300].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        try:
            tg_send(f"❌ <b>Ошибка:</b>\n<code>{err}</code>")
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()
