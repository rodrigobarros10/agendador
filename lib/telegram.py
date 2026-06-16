import requests as _req


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    try:
        r = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        return r.ok
    except Exception:
        return False
