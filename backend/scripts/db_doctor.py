"""Ad-hoc diagnostic: DB connectivity + recent rows in the three key tables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.db.database import get_engine

engine = get_engine()

with engine.connect() as conn:
    print("SELECT NOW():", conn.execute(text("SELECT NOW()")).scalar())

    for table, order, limit in [
        ("complaints", "created_at DESC", 10),
        ("ai_recommendations", "created_at DESC", 10),
        ("status_history", "created_at DESC", 20),
    ]:
        print(f"\n=== {table} (last {limit}) ===")
        try:
            rows = conn.execute(
                text(f"SELECT * FROM {table} ORDER BY {order} LIMIT {limit}")
            ).mappings().all()
            if not rows:
                print("  (no rows)")
            for row in rows:
                limit_row = {k: (str(v)[:60] if v is not None else None) for k, v in dict(row).items()}
                print(" ", limit_row)
        except Exception as exc:
            print("  QUERY FAILED:", type(exc).__name__, str(exc)[:200])

    print("\n=== FK: complaints.student_id ===")
    fks = conn.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'complaints'::regclass AND contype='f'"
    )).all()
    for name, definition in fks:
        print(f"  {name}: {definition}")

    print("\n=== students in users ===")
    users = conn.execute(text(
        "SELECT id, name, role FROM users WHERE role='STUDENT' ORDER BY id"
    )).all()
    for uid, name, role in users:
        print(f"  id={uid} name={name} role={role}")
