"""导入任务三基础数据，并将 ISO 8601 日期转换为 BSON Date。"""

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ENV_FILE = PROJECT_ROOT / "config" / ".env"

load_dotenv(ENV_FILE)

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("MONGODB_DB_NAME", "smart_library")

if not MONGODB_URI:
    raise RuntimeError("未配置 MONGODB_URI")


def load_json(filename):
    path = DATA_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{filename} 顶层结构不是 JSON 数组")

    return data


def parse_iso_date(value):
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def convert_books(records):
    result = []
    for item in records:
        doc = dict(item)

        if "publish_date" in doc:
            doc["publish_date"] = parse_iso_date(doc["publish_date"])

        result.append(doc)

    return result


def convert_readers(records):
    result = []
    for item in records:
        doc = dict(item)

        if "register_date" in doc:
            doc["register_date"] = parse_iso_date(doc["register_date"])

        result.append(doc)

    return result


def convert_borrow_logs(records):
    result = []
    for item in records:
        doc = dict(item)

        if "borrow_date" in doc:
            doc["borrow_date"] = parse_iso_date(doc["borrow_date"])

        if "return_date" in doc:
            doc["return_date"] = parse_iso_date(doc["return_date"])

        result.append(doc)

    return result


def ensure_empty(collection, name):
    count = collection.count_documents({})

    if count != 0:
        raise RuntimeError(
            f"集合 {name} 当前已有 {count} 条文档，"
            "为避免重复导入，程序已停止。"
        )


def main() -> None:
    books_raw = load_json("books.txt")
    readers_raw = load_json("readers.txt")
    borrow_logs_raw = load_json("borrow_logs.txt")

    books = convert_books(books_raw)
    readers = convert_readers(readers_raw)
    borrow_logs = convert_borrow_logs(borrow_logs_raw)

    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
    )

    try:
        client.admin.command("ping")
        db = client[DATABASE_NAME]

        ensure_empty(db.books, "books")
        ensure_empty(db.readers, "readers")
        ensure_empty(db.borrow_logs, "borrow_logs")

        db.books.insert_many(books)
        db.readers.insert_many(readers)
        db.borrow_logs.insert_many(borrow_logs)

        books_count = db.books.count_documents({})
        readers_count = db.readers.count_documents({})
        borrow_logs_count = db.borrow_logs.count_documents({})

        print("\n数据导入完成。")
        print(f"books       : {books_count} / 预期 50")
        print(f"readers     : {readers_count} / 预期 30")
        print(f"borrow_logs : {borrow_logs_count} / 预期 3000")

        sample_book = db.books.find_one(
            {},
            {"_id": 0, "isbn": 1, "publish_date": 1}
        )

        sample_log = db.borrow_logs.find_one(
            {},
            {"_id": 0, "borrow_date": 1, "return_date": 1}
        )

        print("\n日期字段类型抽样：")
        print(
            "books.publish_date:",
            type(sample_book.get("publish_date")).__name__
        )
        print(
            "borrow_logs.borrow_date:",
            type(sample_log.get("borrow_date")).__name__
        )

        if (
            books_count == 50
            and readers_count == 30
            and borrow_logs_count == 3000
        ):
            print("\n[通过] 三个集合的数据量均与源文件一致。")
        else:
            print("\n[异常] 至少一个集合的数据量与预期不一致。")

    finally:
        client.close()


if __name__ == "__main__":
    main()
