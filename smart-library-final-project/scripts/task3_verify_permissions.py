"""验证任务三三类账号的查询、写入和索引管理权限边界。"""

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure


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

if not all([READER_PASSWORD, WRITER_PASSWORD, ADMIN_PASSWORD]):
    raise RuntimeError("请先在 config/.env 中配置三个账号密码")


def connect(username, password):
    """使用指定账号连接业务数据库。"""
    return MongoClient(
        MONGODB_URI,
        username=username,
        password=password,
        authSource=DATABASE_NAME,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
    )


def verify_reader():
    """验证只读账号可以查询，但不能写入数据。"""
    client = connect(
        "libReader",
        READER_PASSWORD,
    )

    try:
        db = client[DATABASE_NAME]

        count = db.books.count_documents({})

        print(
            f"[只读账号] 查询成功："
            f"books 共 {count} 条"
        )

        try:
            db.audit_logs.insert_one(
                {
                    "operate_time": datetime.now(timezone.utc),
                    "operator": "libReader",
                    "operate_type": "PERMISSION_TEST",
                    "target_collection": "audit_logs",
                    "target_id": "reader-test",
                    "operate_detail": "只读账号写入权限测试",
                }
            )

            raise RuntimeError(
                "只读账号竟然能够写入，权限配置异常"
            )

        except OperationFailure as exc:
            if exc.code == 13:
                print(
                    "[只读账号] 写入被拒绝："
                    "权限验证通过"
                )
            else:
                raise

    finally:
        client.close()


def verify_writer():
    """验证读写账号具有正常的数据写入和删除权限。"""
    client = connect(
        "libWriter",
        WRITER_PASSWORD,
    )

    try:
        db = client[DATABASE_NAME]

        result = db.audit_logs.insert_one(
            {
                "operate_time": datetime.now(timezone.utc),
                "operator": "libWriter",
                "operate_type": "PERMISSION_TEST",
                "target_collection": "audit_logs",
                "target_id": "writer-test",
                "operate_detail": "读写账号权限测试",
            }
        )

        db.audit_logs.delete_one(
            {
                "_id": result.inserted_id
            }
        )

        print(
            "[读写账号] 写入和删除测试成功"
        )

    finally:
        client.close()


def verify_admin():
    """
    使用管理账号临时创建并删除索引，
    验证其具备数据库管理权限。
    """
    client = connect(
        "libAdmin",
        ADMIN_PASSWORD,
    )

    try:
        db = client[DATABASE_NAME]

        index_name = (
            "ix_permission_admin_test"
        )

        db.audit_logs.create_index(
            [
                (
                    "operator",
                    ASCENDING,
                )
            ],
            name=index_name,
        )

        db.audit_logs.drop_index(
            index_name
        )

        print(
            "[管理账号] "
            "创建和删除临时索引成功"
        )

    finally:
        client.close()


def main():
    verify_reader()
    verify_writer()
    verify_admin()

    print(
        "\n[通过] 只读、读写、管理三类账号"
        "权限边界均验证成功。"
    )


if __name__ == "__main__":
    main()
