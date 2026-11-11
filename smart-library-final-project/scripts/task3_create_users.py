"""创建任务三只读、读写和数据库管理三类账号。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / "config" / ".env"

load_dotenv(ENV_FILE)

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("MONGODB_DB_NAME", "smart_library")

READER_PASSWORD = os.getenv("MONGODB_READER_PASSWORD")
WRITER_PASSWORD = os.getenv("MONGODB_WRITER_PASSWORD")
ADMIN_PASSWORD = os.getenv("MONGODB_ADMIN_PASSWORD")

if not MONGODB_URI:
    raise RuntimeError("未配置 MONGODB_URI")

if not all(
    [
        READER_PASSWORD,
        WRITER_PASSWORD,
        ADMIN_PASSWORD,
    ]
):
    raise RuntimeError("请先在 config/.env 中配置三个账号密码")


def create_user_if_needed(db, username, password, roles):
    """若账号不存在则创建，避免重复运行产生用户冲突。"""
    users_info = db.command("usersInfo", 1)

    existing_users = {
        user["user"]
        for user in users_info.get("users", [])
    }

    if username in existing_users:
        print(f"[已存在] {username}")
        return

    db.command(
        "createUser",
        username,
        pwd=password,
        roles=roles,
    )

    print(f"[创建成功] {username}")


def main():
    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
    )

    try:
        client.admin.command("ping")
        db = client[DATABASE_NAME]

        # 只读账号仅允许查询业务数据库
        create_user_if_needed(
            db,
            "libReader",
            READER_PASSWORD,
            [
                {
                    "role": "read",
                    "db": DATABASE_NAME,
                }
            ],
        )

        # 读写账号允许正常读取和修改业务数据
        create_user_if_needed(
            db,
            "libWriter",
            WRITER_PASSWORD,
            [
                {
                    "role": "readWrite",
                    "db": DATABASE_NAME,
                }
            ],
        )

        # 管理账号使用 dbOwner，具备当前业务数据库的完整管理权限
        create_user_if_needed(
            db,
            "libAdmin",
            ADMIN_PASSWORD,
            [
                {
                    "role": "dbOwner",
                    "db": DATABASE_NAME,
                }
            ],
        )

        users_info = db.command("usersInfo", 1)

        print("\nsmart_library 用户及角色：")

        for user in users_info.get("users", []):
            roles = [
                f"{role['role']}@{role['db']}"
                for role in user.get("roles", [])
            ]

            print(
                f"  {user['user']}: "
                f"{', '.join(roles)}"
            )

        print("\n[通过] 三类数据库账号创建完成。")

    finally:
        client.close()


if __name__ == "__main__":
    main()
