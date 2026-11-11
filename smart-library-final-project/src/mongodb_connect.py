from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / "config" / ".env"

load_dotenv(ENV_FILE)

DEFAULT_MONGODB_URI: Final = "mongodb://localhost:27017/"
DEFAULT_DATABASE_NAME: Final = "smart_library"


@dataclass(frozen=True)
class MongoSettings:
    uri: str
    database_name: str
    username: str | None
    password: str | None
    auth_source: str
    server_selection_timeout_ms: int
    connect_timeout_ms: int
    socket_timeout_ms: int


def load_settings() -> MongoSettings:
    """读取项目本地 MongoDB 配置。"""
    database_name = os.getenv(
        "MONGODB_DB_NAME",
        DEFAULT_DATABASE_NAME,
    )

    return MongoSettings(
        uri=os.getenv(
            "MONGODB_URI",
            DEFAULT_MONGODB_URI,
        ),
        database_name=database_name,
        username=os.getenv("MONGODB_APP_USER"),
        password=os.getenv("MONGODB_APP_PASSWORD"),
        auth_source=os.getenv(
            "MONGODB_AUTH_SOURCE",
            database_name,
        ),
        server_selection_timeout_ms=int(
            os.getenv(
                "MONGODB_SERVER_SELECTION_TIMEOUT_MS",
                "3000",
            )
        ),
        connect_timeout_ms=int(
            os.getenv(
                "MONGODB_CONNECT_TIMEOUT_MS",
                "3000",
            )
        ),
        socket_timeout_ms=int(
            os.getenv(
                "MONGODB_SOCKET_TIMEOUT_MS",
                "5000",
            )
        ),
    )


def create_client() -> MongoClient:
    """根据当前环境配置创建 MongoDB 客户端。"""
    settings = load_settings()

    # 用户名和密码必须同时配置，避免认证配置缺一项时产生难定位的连接错误
    if bool(settings.username) != bool(settings.password):
        raise RuntimeError(
            "MONGODB_APP_USER 与 MONGODB_APP_PASSWORD 必须同时配置"
        )

    kwargs = {
        "serverSelectionTimeoutMS":
            settings.server_selection_timeout_ms,
        "connectTimeoutMS":
            settings.connect_timeout_ms,
        "socketTimeoutMS":
            settings.socket_timeout_ms,
    }

    if settings.username and settings.password:
        kwargs.update(
            {
                "username": settings.username,
                "password": settings.password,
                "authSource": settings.auth_source,
            }
        )

    return MongoClient(
        settings.uri,
        **kwargs,
    )


def get_database(
    client: MongoClient,
) -> Database:
    """返回项目统一使用的业务数据库。"""
    settings = load_settings()
    return client[settings.database_name]


def check_connection(
    client: MongoClient,
) -> bool:
    """使用 ping 判断当前账号是否能够访问 MongoDB。"""
    try:
        client.admin.command("ping")
        return True
    except PyMongoError:
        return False


if __name__ == "__main__":
    client = create_client()

    try:
        settings = load_settings()

        if check_connection(client):
            print(
                f"MongoDB 连接成功，"
                f"当前业务数据库：{settings.database_name}"
            )
        else:
            print(
                "MongoDB 连接失败，请检查服务状态、"
                "认证账号和 config/.env"
            )

    finally:
        client.close()