"""warden auth and row level security

Revision ID: 66ae9ccc1b8a
Revises: 53c0591d0916
Create Date: 2026-10-26 21:54:33.024583
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.core.config import settings


revision: str = '66ae9ccc1b8a'
down_revision: Union[str, None] = '53c0591d0916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _app_policy(
    name: str,
    table: str,
    command: str,
    *,
    using: str | None = None,
    check: str | None = None,
) -> None:
    role = op.get_bind().dialect.identifier_preparer.quote(settings.application_db_role)
    sql = f'CREATE POLICY "{name}" ON public."{table}" FOR {command} TO {role}'
    if using:
        sql += f" USING ({using})"
    if check:
        sql += f" WITH CHECK ({check})"
    op.execute(sa.text(sql))


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_user_id", sa.Uuid(), nullable=True))
    op.create_index("ix_users_auth_user_id", "users", ["auth_user_id"], unique=True)
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "users", "workers", "complaints", "tasks", "status_history",
            "ai_recommendations", "alerts", "alembic_version",
        ):
            op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))

        # The FastAPI database role receives an identity context only after
        # the request token or demo user has been validated server-side.
        app_role = "current_setting('hosteldesk.role', true)"
        app_user = "NULLIF(current_setting('hosteldesk.user_id', true), '')::integer"
        auth_user = "NULLIF(current_setting('hosteldesk.auth_user_id', true), '')::uuid"
        warden = f"{app_role} = 'WARDEN'"
        system = f"{app_role} = 'SYSTEM'"
        student = f"{app_role} = 'STUDENT'"
        worker = f"{app_role} = 'WORKER'"
        worker_owns = (
            f"EXISTS (SELECT 1 FROM public.workers w "
            f"WHERE w.id = {{worker_id}} AND w.user_id = {app_user})"
        )
        complaint_worker_owns = worker_owns.format(worker_id="complaints.approved_worker_id")
        task_worker_owns = worker_owns.format(worker_id="tasks.worker_id")
        history_worker_owns = (
            "EXISTS (SELECT 1 FROM public.complaints c "
            "WHERE c.id = status_history.complaint_id AND "
            + worker_owns.format(worker_id="c.approved_worker_id")
            + ")"
        )
        history_student_owns = (
            f"EXISTS (SELECT 1 FROM public.complaints c "
            f"WHERE c.id = status_history.complaint_id AND c.student_id = {app_user})"
        )

        _app_policy(
            "users_app_select", "users", "SELECT",
            using=f"{system} OR {warden} OR id = {app_user} OR "
                  f"({app_role} IN ('LOOKUP', 'ONBOARDING') AND auth_user_id = {auth_user})",
        )
        _app_policy(
            "users_app_insert", "users", "INSERT",
            check=f"{system} OR ({app_role} = 'ONBOARDING' AND role IN ('STUDENT', 'WARDEN', 'WORKER') "
                  f"AND auth_user_id = {auth_user})",
        )
        _app_policy(
            "workers_app_insert", "workers", "INSERT",
            check=f"{system} OR ({app_role} = 'ONBOARDING' AND user_id = "
                  f"(SELECT id FROM public.users WHERE auth_user_id = {auth_user} AND role = 'WORKER'))",
        )
        _app_policy(
            "workers_app_select", "workers", "SELECT",
            using=f"{system} OR {warden} OR ({worker} AND user_id = {app_user})",
        )
        _app_policy(
            "complaints_app_select", "complaints", "SELECT",
            using=f"{system} OR {warden} OR ({student} AND student_id = {app_user}) "
                  f"OR ({worker} AND {complaint_worker_owns})",
        )
        _app_policy(
            "complaints_app_insert", "complaints", "INSERT",
            check=f"{system} OR ({student} AND student_id = {app_user} "
                  "AND status = 'SUBMITTED' AND approved_worker_id IS NULL)",
        )
        _app_policy(
            "complaints_app_update", "complaints", "UPDATE",
            using=f"{system} OR {warden} OR ({worker} AND {complaint_worker_owns})",
            check=f"{system} OR {warden} OR ({worker} AND {complaint_worker_owns})",
        )
        _app_policy(
            "tasks_app_select", "tasks", "SELECT",
            using=f"{system} OR {warden} OR ({worker} AND {task_worker_owns})",
        )
        _app_policy(
            "tasks_app_insert", "tasks", "INSERT", check=f"{system} OR {warden}"
        )
        _app_policy(
            "tasks_app_update", "tasks", "UPDATE",
            using=f"{system} OR {warden} OR ({worker} AND {task_worker_owns})",
            check=f"{system} OR {warden} OR ({worker} AND {task_worker_owns})",
        )
        _app_policy(
            "status_history_app_select", "status_history", "SELECT",
            using=f"{system} OR {warden} OR ({student} AND {history_student_owns}) "
                  f"OR ({worker} AND {history_worker_owns})",
        )
        _app_policy(
            "status_history_app_insert", "status_history", "INSERT",
            check=f"{system} OR {warden} OR ({student} AND changed_by = {app_user} "
                  f"AND new_status = 'SUBMITTED' "
                  f"AND EXISTS (SELECT 1 FROM public.complaints c "
                  f"WHERE c.id = status_history.complaint_id AND c.student_id = {app_user})) "
                  f"OR ({worker} AND changed_by = {app_user} AND {history_worker_owns})",
        )
        _app_policy(
            "ai_recommendations_app_select", "ai_recommendations", "SELECT",
            using=f"{system} OR {warden}",
        )
        _app_policy(
            "ai_recommendations_app_insert", "ai_recommendations", "INSERT", check=system
        )
        _app_policy(
            "alerts_app_select", "alerts", "SELECT", using=f"{system} OR {warden}"
        )
        _app_policy(
            "alerts_app_insert", "alerts", "INSERT", check=f"{system} OR {warden}"
        )
        _app_policy(
            "alerts_app_update", "alerts", "UPDATE",
            using=f"{system} OR {warden}", check=f"{system} OR {warden}",
        )
        # Direct Supabase Data API reads are Warden-only via server-set claims.
        warden_claim = "(auth.jwt() -> 'app_metadata' ->> 'role') = 'WARDEN'"
        op.execute(sa.text(
            "CREATE POLICY users_warden_or_self_select ON public.users FOR SELECT TO authenticated "
            f"USING (auth_user_id = (SELECT auth.uid()) OR {warden_claim})"
        ))
        for table in ("workers", "complaints", "tasks", "status_history", "ai_recommendations", "alerts"):
            op.execute(sa.text(
                f'CREATE POLICY "{table}_warden_select" ON public."{table}" '
                f"FOR SELECT TO authenticated USING ({warden_claim})"
            ))
        op.execute(sa.text(
            "GRANT SELECT ON public.users, public.workers, public.complaints, public.tasks, "
            "public.status_history, public.ai_recommendations, public.alerts TO authenticated"
        ))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(
            "REVOKE SELECT ON public.users, public.workers, public.complaints, public.tasks, "
            "public.status_history, public.ai_recommendations, public.alerts FROM authenticated"
        ))
        for table in ("workers", "complaints", "tasks", "status_history", "ai_recommendations", "alerts"):
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_warden_select" ON public."{table}"'))
        op.execute(sa.text("DROP POLICY IF EXISTS users_warden_or_self_select ON public.users"))
        for table in (
            "users", "workers", "complaints", "tasks", "status_history",
            "ai_recommendations", "alerts", "alembic_version",
        ):
            op.execute(sa.text(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_users_auth_user_id", table_name="users")
    op.drop_column("users", "auth_user_id")
