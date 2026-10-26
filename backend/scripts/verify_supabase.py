"""One-shot Supabase integration check.

Run AFTER filling SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / DATABASE_URL in
backend/.env, while the bucket `complaint-photos` exists (SQL below creates it).

Creates a tiny private object, reads it back, produces a short-lived signed
URL, then deletes it. Also pings the Supabase PostgreSQL database.

Usage:
    python scripts/verify_supabase.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on sys.path

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.database import get_engine  # noqa: E402


def main() -> int:
    if not settings.supabase_configured:
        print("FAIL: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env first.")
        return 1

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    bucket = settings.supabase_storage_bucket
    storage = client.storage.from_(bucket)

    print(f"1/3 listing buckets ...", end=" ")
    buckets = client.storage.list_buckets()
    names = [b.name for b in buckets]
    print(f"found {len(names)}")
    if bucket not in names:
        print(
            f"FAIL: bucket '{bucket}' does not exist. Create it in the Supabase dashboard\n"
            f"       (Storage > New bucket > Private), or run this SQL in the SQL editor:\n\n"
            f'    insert into storage.buckets (id, name, public) values (\'{bucket}\', \'{bucket}\', false);\n'
        )
        return 1

    key = "smoke-tests/hosteldesk-verify.txt"
    print(f"2/3 upload + download + signed URL under '{bucket}/{key}' ...")
    storage.upload(key, b"hosteldesk connectivity smoke test", {"content-type": "text/plain"})
    data = storage.download(key)
    if data != b"hosteldesk connectivity smoke test":
        print("FAIL: uploaded object does not match.")
        return 1
    signed = storage.create_signed_url(key, 60)
    signed_url = signed.get("signedURL", "") if isinstance(signed, dict) else ""
    if not signed_url:
        print(f"FAIL: no signed URL returned: {signed}")
        return 1
    print(f"     signed url ok -> {signed_url[:80]}...")
    client.storage.from_(bucket).remove([key])
    print("     cleanup ok")

    print(f"3/3 database ping via DATABASE_URL ...", end=" ")
    with get_engine().connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar()
    print("connected")
    print(f"     server: {str(version)[:60]}...")

    print("\nOK - Supabase is fully wired: Postgres reachable, Bucket exists, Storage I/O works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
