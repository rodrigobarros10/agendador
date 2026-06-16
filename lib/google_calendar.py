import os
from datetime import datetime

import requests as _req
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
_AUTH_URL  = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def auth_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id":     os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    return _AUTH_URL + "?" + _req.compat.urlencode(params)


def exchange_code(code: str, redirect_uri: str) -> tuple[str | None, str | None]:
    try:
        resp = _req.post(_TOKEN_URL, data={
            "code":          code,
            "client_id":     os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
        resp.raise_for_status()
        data = resp.json()
        return data.get("access_token"), data.get("refresh_token")
    except Exception as e:
        print(f"[google_calendar] exchange_code error: {e}")
        return None, None


def get_user_email(access_token: str) -> str:
    try:
        resp = _req.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return resp.json().get("email", "")
    except Exception:
        return ""


def create_event(
    refresh_token: str,
    summary: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    timezone: str = "America/Sao_Paulo",
) -> str | None:
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=_TOKEN_URL,
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=SCOPES,
        )
        creds.refresh(Request())
        service = build("calendar", "v3", credentials=creds)
        event = {
            "summary":     summary,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
            "end":   {"dateTime": end_dt.isoformat(),   "timeZone": timezone},
        }
        result = service.events().insert(calendarId="primary", body=event).execute()
        return result.get("htmlLink")
    except Exception as e:
        print(f"[google_calendar] create_event error: {e}")
        return None
