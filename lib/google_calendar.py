import os
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def _flow(redirect_uri: str) -> Flow:
    config = {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)


def auth_url(redirect_uri: str, state: str) -> str:
    url, _ = _flow(redirect_uri).authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return url


def exchange_code(code: str, redirect_uri: str) -> tuple[str | None, str | None]:
    try:
        flow = _flow(redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials
        return creds.token, creds.refresh_token
    except Exception:
        return None, None


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
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=SCOPES,
        )
        creds.refresh(Request())
        service = build("calendar", "v3", credentials=creds)
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
        }
        result = service.events().insert(calendarId="primary", body=event).execute()
        return result.get("htmlLink")
    except Exception:
        return None
