"""MongoDB 连接配置与统一入口。"""

import os
from typing import Optional, Tuple

from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError, ServerSelectionTimeoutError


HOST = "192.168.121.134"
PORT = 27017
DB_NAME = "library"
USERNAME = "libWriter"
AUTH_SOURCE = "library"
PASSWORD = os.getenv("MONGO_PASSWORD")

_client: Optional[MongoClient] = None


def _get_password() -> str:
    """读取密码；缺少配置时给出容易理解的中文提示。"""
    password = os.getenv("MONGO_PASSWORD") or PASSWORD
    if not password:
        raise RuntimeError(
            "未设置 MongoDB 密码。请先设置环境变量 MONGO_PASSWORD，再启动程序。"
        )
    return password


def get_client() -> MongoClient:
    """获取本程序共用的 MongoClient，不主动执行数据库操作。"""
    global _client
    if _client is None:
        _client = MongoClient(
            HOST,
            PORT,
            username=USERNAME,
            password=_get_password(),
            authSource=AUTH_SOURCE,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
    return _client


def get_db():
    """获取 library 数据库对象。"""
    return get_client()[DB_NAME]


def test_connection() -> Tuple[bool, str]:
    """测试服务器连接并返回（是否成功，中文说明）。"""
    try:
        get_client().admin.command("ping")
        return True, "MongoDB 连接成功"
    except RuntimeError as exc:
        close_client()
        return False, str(exc)
    except OperationFailure as exc:
        close_client()
        detail = exc.details.get("errmsg") if exc.details else str(exc)
        return False, f"MongoDB 认证失败，请检查用户名、密码和认证库：{detail}"
    except ServerSelectionTimeoutError:
        close_client()
        return False, f"MongoDB 连接失败：无法连接到 {HOST}:{PORT}，请检查服务和网络。"
    except PyMongoError as exc:
        close_client()
        return False, f"MongoDB 连接失败：{exc}"


def close_client() -> None:
    """关闭共用客户端。"""
    global _client
    if _client is not None:
        _client.close()
        _client = None
