"""本地业务样例数据库初始化。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings
from app.services.seed_data import EMPLOYEES, PAYROLL_RECORDS


def ensure_business_database() -> None:
    """创建并填充本地 SQLite 样例数据库。"""
    settings = get_settings()
    db_path = Path(settings.business_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT NOT NULL,
                manager_id TEXT,
                phone TEXT NOT NULL,
                id_card TEXT NOT NULL,
                annual_leave INTEGER NOT NULL,
                contract_end TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS payroll_records (
                record_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                payroll_month TEXT NOT NULL,
                base_salary REAL NOT NULL,
                bonus REAL NOT NULL,
                allowance REAL NOT NULL,
                tax REAL NOT NULL,
                social_security REAL NOT NULL,
                total_package REAL NOT NULL
            )
            """
        )
        cursor.execute("DELETE FROM employees")
        cursor.execute("DELETE FROM payroll_records")

        cursor.executemany(
            """
            INSERT INTO employees (
                user_id, username, name, role, department, manager_id, phone, id_card, annual_leave, contract_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    employee["user_id"],
                    employee["username"],
                    employee["name"],
                    employee["role"],
                    employee["department"],
                    employee["manager_id"],
                    employee["phone"],
                    employee["id_card"],
                    employee["annual_leave"],
                    employee["contract_end"],
                )
                for employee in EMPLOYEES
            ],
        )
        cursor.executemany(
            """
            INSERT INTO payroll_records (
                record_id, user_id, payroll_month, base_salary, bonus, allowance, tax, social_security, total_package
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record["record_id"],
                    record["user_id"],
                    record["payroll_month"],
                    record["base_salary"],
                    record["bonus"],
                    record["allowance"],
                    record["tax"],
                    record["social_security"],
                    record["total_package"],
                )
                for record in PAYROLL_RECORDS
            ],
        )
        connection.commit()
    finally:
        connection.close()


def build_database_engine(database_url: str) -> Engine:
    """按数据库类型创建 SQLAlchemy Engine。"""
    settings = get_settings()
    if database_url.startswith("sqlite"):
        return create_engine(database_url, future=True)
    return create_engine(
        database_url,
        future=True,
        connect_args={"connect_timeout": settings.postgres_connect_timeout_seconds},
        pool_pre_ping=True,
    )


def ensure_postgres_business_database() -> None:
    """当 PostgreSQL 可用时创建并填充业务样例表。"""
    settings = get_settings()
    engine = build_database_engine(settings.postgres_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS employees (
                        user_id TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        name TEXT NOT NULL,
                        role TEXT NOT NULL,
                        department TEXT NOT NULL,
                        manager_id TEXT,
                        phone TEXT NOT NULL,
                        id_card TEXT NOT NULL,
                        annual_leave INTEGER NOT NULL,
                        contract_end TEXT NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS payroll_records (
                        record_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        payroll_month TEXT NOT NULL,
                        base_salary DOUBLE PRECISION NOT NULL,
                        bonus DOUBLE PRECISION NOT NULL,
                        allowance DOUBLE PRECISION NOT NULL,
                        tax DOUBLE PRECISION NOT NULL,
                        social_security DOUBLE PRECISION NOT NULL,
                        total_package DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            connection.execute(text("DELETE FROM employees"))
            connection.execute(text("DELETE FROM payroll_records"))
            connection.execute(
                text(
                    """
                    INSERT INTO employees (
                        user_id, username, name, role, department, manager_id, phone, id_card, annual_leave, contract_end
                    ) VALUES (
                        :user_id, :username, :name, :role, :department, :manager_id, :phone, :id_card, :annual_leave, :contract_end
                    )
                    """
                ),
                EMPLOYEES,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO payroll_records (
                        record_id, user_id, payroll_month, base_salary, bonus, allowance, tax, social_security, total_package
                    ) VALUES (
                        :record_id, :user_id, :payroll_month, :base_salary, :bonus, :allowance, :tax, :social_security, :total_package
                    )
                    """
                ),
                PAYROLL_RECORDS,
            )
    finally:
        engine.dispose()


@contextmanager
def get_sqlite_connection() -> Iterator[sqlite3.Connection]:
    """获取本地样例数据库连接。"""
    ensure_business_database()
    connection = sqlite3.connect(get_settings().business_db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()
