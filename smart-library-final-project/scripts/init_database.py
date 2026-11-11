"""创建任务三所需集合，不删除或覆盖已存在的数据。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / "config" / ".env"

load_dotenv(ENV_FILE)

mongodb_uri = os.getenv("MONGODB_URI")
database_name = os.getenv("MONGODB_DB_NAME", "smart_library")


def main() -> None:
    """按需创建集合并输出初始化结果。"""
    if not mongodb_uri:
        raise RuntimeError("未配置 MONGODB_URI")

    client = MongoClient(
        mongodb_uri,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
    )

    try:
        client.admin.command("ping")
        db = client[database_name]

        required_collections = [
            "books",
            "readers",
            "borrow_logs",
            "audit_logs",
            "stat_result",
        ]
        existing = set(db.list_collection_names())

        for collection_name in required_collections:
            if collection_name not in existing:
                db.create_collection(collection_name)
                print(f"[创建] {collection_name}")
            else:
                print(f"[已存在] {collection_name}")

        print("\n数据库初始化完成。")
        print(f"数据库：{database_name}")
        print("集合：")
        for name in sorted(db.list_collection_names()):
            print(f"  - {name}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
