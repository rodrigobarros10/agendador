import requests as _req


def send_telegram(bot_token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """Returns (success, error_description)."""
    try:
        r = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        if r.ok:
            return True, ""
        data = r.json()
        return False, data.get("description", f"HTTP {r.status_code}")
    except Exception as e:
        return False, str(e)
