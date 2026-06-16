import os
from supabase import create_client, Client

_anon: Client | None = None
_admin: Client | None = None


def get_supabase() -> Client:
    global _anon
    if _anon is None:
        _anon = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    return _anon


def get_supabase_admin() -> Client:
    global _admin
    if _admin is None:
        _admin = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    return _admin
