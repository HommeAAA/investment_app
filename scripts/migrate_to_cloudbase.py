#!/usr/bin/env python3
"""
Migrate legacy SQL data to CloudBase-shaped collections.

Outputs collections:
- legacy_users
- investments
- shares
- operation_logs
- symbol_cache

By default it exports JSON files. If --mongo-uri is provided, it also writes
records into CloudBase Mongo collections directly.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def legacy_uid(username: str) -> str:
    return f"legacy:{username.strip()}"


def to_iso(value: Any) -> str:
    if value is None:
        return now_iso()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


@dataclass
class ExportBundle:
    legacy_users: list[dict[str, Any]]
    investments: list[dict[str, Any]]
    shares: list[dict[str, Any]]
    operation_logs: list[dict[str, Any]]
    symbol_cache: list[dict[str, Any]]


def table_exists(insp, table_name: str) -> bool:
    return table_name in insp.get_table_names()


def table_columns(insp, table_name: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table_name)}


def fetch_rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = conn.execute(text(sql), params or {})
    return [dict(row._mapping) for row in result]


def export_from_sql(source_url: str) -> ExportBundle:
    engine = create_engine(source_url)
    insp = inspect(engine)

    legacy_users: list[dict[str, Any]] = []
    investments: list[dict[str, Any]] = []
    shares: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []

    with engine.connect() as conn:
        if table_exists(insp, "users"):
            for row in fetch_rows(conn, "SELECT username, password_hash, created_at FROM users"):
                username = str(row.get("username") or "").strip()
                if not username:
                    continue
                legacy_users.append(
                    {
                        "username": username,
                        "passwordHash": str(row.get("password_hash") or ""),
                        "migratedAt": now_iso(),
                        "boundUid": "",
                        "createdAt": to_iso(row.get("created_at")),
                    }
                )

        if table_exists(insp, "investments"):
            cols = table_columns(insp, "investments")
            owner_col = "owner_username" if "owner_username" in cols else ("user" if "user" in cols else None)

            inv_cols = [
                "id",
                "investor",
                "market",
                "symbol_code",
                "symbol_name",
                "channel",
                "cost_price",
                "quantity",
                "update_time",
            ]
            if owner_col:
                inv_cols.append(owner_col)

            sql = f"SELECT {', '.join(inv_cols)} FROM investments"
            for row in fetch_rows(conn, sql):
                owner_username = str(row.get(owner_col) or "").strip() if owner_col else ""
                if not owner_username:
                    owner_username = "admin"

                investments.append(
                    {
                        "legacySourceId": str(row.get("id") or ""),
                        "ownerUid": legacy_uid(owner_username),
                        "ownerLegacyUsername": owner_username,
                        "investor": str(row.get("investor") or owner_username),
                        "market": str(row.get("market") or "美股"),
                        "symbolCode": str(row.get("symbol_code") or "").upper(),
                        "symbolName": str(row.get("symbol_name") or row.get("symbol_code") or ""),
                        "channel": str(row.get("channel") or ""),
                        "costPrice": float(row.get("cost_price") or 0),
                        "quantity": float(row.get("quantity") or 0),
                        "updatedAt": to_iso(row.get("update_time")),
                    }
                )

        if table_exists(insp, "shares"):
            cols = table_columns(insp, "shares")
            perm_col = "permission" if "permission" in cols else None
            sel_cols = ["owner", "shared_with", "created_at"]
            if perm_col:
                sel_cols.append(perm_col)
            sql = f"SELECT {', '.join(sel_cols)} FROM shares"
            for row in fetch_rows(conn, sql):
                owner = str(row.get("owner") or "").strip()
                shared_with = str(row.get("shared_with") or "").strip()
                if not owner or not shared_with:
                    continue
                shares.append(
                    {
                        "ownerUid": legacy_uid(owner),
                        "ownerLegacyUsername": owner,
                        "sharedWithUid": legacy_uid(shared_with),
                        "sharedWithLegacyUsername": shared_with,
                        "permission": "edit" if str(row.get("permission") or "") == "edit" else "read",
                        "createdAt": to_iso(row.get("created_at")),
                    }
                )

        if table_exists(insp, "operation_logs"):
            for row in fetch_rows(
                conn,
                """
                SELECT id, entity_type, entity_id, action, operator, owner,
                       changed_fields, before_data, after_data, action_time
                FROM operation_logs
                """,
            ):
                owner = str(row.get("owner") or row.get("operator") or "admin").strip()
                operator = str(row.get("operator") or owner).strip()
                logs.append(
                    {
                        "legacySourceId": str(row.get("id") or ""),
                        "entityType": str(row.get("entity_type") or ""),
                        "entityId": str(row.get("entity_id") or ""),
                        "action": str(row.get("action") or ""),
                        "operatorUid": legacy_uid(operator),
                        "operatorLegacyUsername": operator,
                        "ownerUid": legacy_uid(owner),
                        "ownerLegacyUsername": owner,
                        "changedFields": str(row.get("changed_fields") or ""),
                        "beforeData": str(row.get("before_data") or ""),
                        "afterData": str(row.get("after_data") or ""),
                        "actionTime": to_iso(row.get("action_time")),
                    }
                )

        if table_exists(insp, "symbol_cache"):
            for row in fetch_rows(
                conn,
                "SELECT market, symbol_code, symbol_name, source, updated_at FROM symbol_cache",
            ):
                symbols.append(
                    {
                        "market": str(row.get("market") or ""),
                        "symbolCode": str(row.get("symbol_code") or "").upper(),
                        "symbolName": str(row.get("symbol_name") or row.get("symbol_code") or ""),
                        "source": str(row.get("source") or "migration"),
                        "updatedAt": to_iso(row.get("updated_at")),
                    }
                )

    return ExportBundle(
        legacy_users=legacy_users,
        investments=investments,
        shares=shares,
        operation_logs=logs,
        symbol_cache=symbols,
    )


def write_json(bundle: ExportBundle, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "legacy_users": bundle.legacy_users,
        "investments": bundle.investments,
        "shares": bundle.shares,
        "operation_logs": bundle.operation_logs,
        "symbol_cache": bundle.symbol_cache,
    }
    for name, rows in mapping.items():
        path = out_dir / f"{name}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)


def write_mongo(bundle: ExportBundle, mongo_uri: str, truncate: bool) -> None:
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError("未安装 pymongo，无法写入 Mongo。请先执行: pip install pymongo") from exc

    client = MongoClient(mongo_uri)
    db = client.get_default_database()
    if db is None:
        raise RuntimeError("Mongo URI 未包含默认数据库名，请在 URI 末尾加 /<db_name>")

    mapping = {
        "legacy_users": bundle.legacy_users,
        "investments": bundle.investments,
        "shares": bundle.shares,
        "operation_logs": bundle.operation_logs,
        "symbol_cache": bundle.symbol_cache,
    }

    for col, rows in mapping.items():
        collection = db[col]
        if truncate:
            collection.delete_many({})
        if rows:
            collection.insert_many(rows, ordered=False)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy SQL data to CloudBase collections")
    parser.add_argument("--source", required=True, help="SQLAlchemy source URL, e.g. sqlite:///testApp.db")
    parser.add_argument(
        "--out-dir",
        default="cloudbase_migration_out",
        help="Directory for JSON export files",
    )
    parser.add_argument(
        "--mongo-uri",
        default="",
        help="Optional CloudBase Mongo URI. If provided, script writes directly to collections.",
    )
    parser.add_argument("--truncate", action="store_true", help="Clear target collections before insert")
    return parser.parse_args()



def main() -> None:
    args = parse_args()
    bundle = export_from_sql(args.source)

    out_dir = Path(args.out_dir)
    write_json(bundle, out_dir)

    print("JSON export completed:")
    print(f"  - {out_dir / 'legacy_users.json'} ({len(bundle.legacy_users)} rows)")
    print(f"  - {out_dir / 'investments.json'} ({len(bundle.investments)} rows)")
    print(f"  - {out_dir / 'shares.json'} ({len(bundle.shares)} rows)")
    print(f"  - {out_dir / 'operation_logs.json'} ({len(bundle.operation_logs)} rows)")
    print(f"  - {out_dir / 'symbol_cache.json'} ({len(bundle.symbol_cache)} rows)")

    if args.mongo_uri:
        write_mongo(bundle, args.mongo_uri, args.truncate)
        print("Mongo write completed.")



if __name__ == "__main__":
    main()
