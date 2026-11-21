"""Alembic migrations: round trip, model parity and database-level constraints."""

from __future__ import annotations

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.integration.conftest import reset_schema
from via_api.db import alembic_config
from via_api.models import (
    ActivityLog,
    Base,
    Organization,
    Project,
    ProjectMembership,
    User,
)
from via_api.models.enums import ProjectRole, ProjectVisibility

EXPECTED_TABLES = {
    "users",
    "user_sessions",
    "password_reset_tokens",
    "organizations",
    "organization_memberships",
    "projects",
    "project_memberships",
    "designs",
    "design_revisions",
    "design_files",
    "upload_records",
    "pcb_layers",
    "pcb_nets",
    "pcb_components",
    "pcb_geometry",
    "analysis_runs",
    "activity_logs",
    "data_consents",
}


def test_upgrade_downgrade_upgrade_round_trip(database_url, migrated_engine):
    cfg = alembic_config(database_url)
    engine = create_engine(database_url)
    try:
        command.downgrade(cfg, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        command.upgrade(cfg, "head")
        assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
    finally:
        engine.dispose()


def test_models_match_migrations(migrated_engine):
    with migrated_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Models and migrations differ; generate a migration: {diff}"


def test_all_primary_keys_are_uuid_and_timestamps_are_utc(migrated_engine):
    insp = inspect(migrated_engine)
    for table in EXPECTED_TABLES:
        cols = {c["name"]: c for c in insp.get_columns(table)}
        assert str(cols["id"]["type"]) == "UUID", table
        for name in ("created_at", "updated_at"):
            if name in cols:
                assert getattr(cols[name]["type"], "timezone", False), (table, name)


def test_foreign_keys_are_indexed_where_queried(migrated_engine):
    insp = inspect(migrated_engine)

    def indexed(table: str, column: str) -> bool:
        idx = [i["column_names"] for i in insp.get_indexes(table)]
        uqs = [u["column_names"] for u in insp.get_unique_constraints(table)]
        return any(cols and cols[0] == column for cols in idx + uqs)

    for table, column in [
        ("projects", "organization_id"),
        ("projects", "owner_id"),
        ("project_memberships", "project_id"),
        ("project_memberships", "user_id"),
        ("organization_memberships", "organization_id"),
        ("organization_memberships", "user_id"),
        ("designs", "project_id"),
        ("design_revisions", "design_id"),
        ("design_revisions", "project_id"),
        ("design_files", "revision_id"),
        ("pcb_components", "revision_id"),
        ("pcb_nets", "revision_id"),
        ("pcb_layers", "revision_id"),
        ("activity_logs", "project_id"),
        ("user_sessions", "user_id"),
    ]:
        assert indexed(table, column), f"{table}.{column} has no leading index"


def _user(db: Session, email: str) -> User:
    user = User(email=email, password_hash="x", display_name=email.split("@")[0])
    db.add(user)
    db.flush()
    return user


def _project(db: Session, owner: User) -> Project:
    org = Organization(name="Personal", slug=f"p-{uuid.uuid4().hex[:12]}", is_personal=True, created_by_id=owner.id)
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, owner_id=owner.id, name="Board")
    db.add(project)
    db.flush()
    return project


def test_projects_are_private_by_default_at_the_database_level(db):
    owner = _user(db, "a@example.com")
    project = _project(db, owner)
    db.execute(
        text("INSERT INTO projects (id, organization_id, owner_id, name) VALUES (:id, :org, :owner, 'raw')"),
        {"id": uuid.uuid4(), "org": project.organization_id, "owner": owner.id},
    )
    visibilities = set(db.scalars(select(Project.visibility)))
    assert visibilities == {ProjectVisibility.PRIVATE}


def test_check_constraints_reject_unknown_enum_values(db):
    owner = _user(db, "b@example.com")
    project = _project(db, owner)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("UPDATE projects SET visibility = 'public' WHERE id = :id"), {"id": project.id})


def test_email_is_unique(db):
    _user(db, "dup@example.com")
    with pytest.raises(IntegrityError), db.begin_nested():
        _user(db, "dup@example.com")


def test_project_membership_is_unique_per_user(db):
    owner = _user(db, "c@example.com")
    project = _project(db, owner)
    db.add(ProjectMembership(project_id=project.id, user_id=owner.id, role=ProjectRole.OWNER))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(ProjectMembership(project_id=project.id, user_id=owner.id, role=ProjectRole.VIEWER))
        db.flush()


def test_deleting_a_project_cascades_memberships_but_keeps_audit_log(db):
    owner = _user(db, "d@example.com")
    project = _project(db, owner)
    db.add(ProjectMembership(project_id=project.id, user_id=owner.id, role=ProjectRole.OWNER))
    db.add(ActivityLog(actor_id=owner.id, project_id=project.id, action="project.created"))
    db.flush()
    db.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})
    assert db.scalar(select(ProjectMembership).where(ProjectMembership.project_id == project.id)) is None
    log = db.scalar(select(ActivityLog).where(ActivityLog.action == "project.created"))
    assert log is not None and log.project_id is None  # audit entry survives, reference cleared


def test_user_with_projects_cannot_be_hard_deleted(db):
    owner = _user(db, "e@example.com")
    _project(db, owner)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner.id})


def test_schema_reset_helper_leaves_a_clean_database(database_url, migrated_engine):
    # Guard for the test harness itself: re-running the session setup must work.
    engine = create_engine(database_url)
    try:
        reset_schema(engine)
        command.upgrade(alembic_config(database_url), "head")
        assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
    finally:
        engine.dispose()
