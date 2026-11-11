from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bson import json_util
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from audit_manager import AuditManager


class BookManager:
    def __init__(
        self,
        db: Database,
        audit_manager: AuditManager,
    ):
        self.collection = db["books"]
        self.borrow_logs = db["borrow_logs"]
        self.audit = audit_manager

    def search_by_category_price(
        self,
        category: str,
        min_price: float,
        max_price: float,
    ) -> list[dict[str, Any]]:
        if min_price > max_price:
            raise ValueError("最低价格不能大于最高价格")

        query = {
            "category": category,
            "price": {
                "$gte": min_price,
                "$lte": max_price,
            },
        }

        return list(
            self.collection.find(
                query,
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "category": 1,
                    "price": 1,
                },
            ).sort("price", 1)
        )

    def search_by_tags(
        self,
        tags: list[str],
    ) -> list[dict[str, Any]]:
        cleaned_tags = [
            tag.strip()
            for tag in tags
            if tag.strip()
        ]

        if not cleaned_tags:
            raise ValueError("至少需要提供一个标签")

        # $all 要求数组中同时具有所有指定标签
        return list(
            self.collection.find(
                {
                    "tags": {
                        "$all": cleaned_tags,
                    }
                },
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "tags": 1,
                },
            )
        )

    def search_by_title(
        self,
        keyword: str,
    ) -> list[dict[str, Any]]:
        keyword = keyword.strip()

        if not keyword:
            raise ValueError("书名关键词不能为空")

        # 转义用户输入，避免其中的特殊字符被当作正则语法
        pattern = re.escape(keyword)

        return list(
            self.collection.find(
                {
                    "title": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "author": 1,
                },
            )
        )

    def search_by_publish_year(
        self,
        start_year: int,
        end_year: int,
    ) -> list[dict[str, Any]]:
        if start_year > end_year:
            raise ValueError("起始年份不能大于结束年份")

        china_tz = timezone(timedelta(hours=8))

        start_date = datetime(
            start_year,
            1,
            1,
            tzinfo=china_tz,
        )

        # 左闭右开区间可以避免手动设置年末 23:59:59 带来的边界问题
        end_date = datetime(
            end_year + 1,
            1,
            1,
            tzinfo=china_tz,
        )

        return list(
            self.collection.find(
                {
                    "publish_date": {
                        "$gte": start_date,
                        "$lt": end_date,
                    }
                },
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "publish_date": 1,
                },
            ).sort("publish_date", 1)
        )

    def find_missing_tags(
        self,
    ) -> list[dict[str, Any]]:
        return list(
            self.collection.find(
                {
                    "tags": {
                        "$exists": False,
                    }
                },
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                },
            )
        )

    def top_rated(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        return list(
            self.collection.find(
                {},
                {
                    "_id": 0,
                    "title": 1,
                    "author": 1,
                    "rating": 1,
                },
            )
            .sort(
                [
                    ("rating", -1),
                    # 同分时按书名排序，保证多次运行结果顺序稳定
                    ("title", 1),
                ]
            )
            .limit(limit)
        )

    def get_by_isbn(
        self,
        isbn: str,
    ) -> dict[str, Any] | None:
        return self.collection.find_one(
            {
                "isbn": isbn.strip(),
            },
            {
                "_id": 0,
            },
        )

    def add_book(
        self,
        book: dict[str, Any],
    ) -> None:
        isbn = str(
            book.get("isbn", "")
        ).strip()

        title = str(
            book.get("title", "")
        ).strip()

        if not isbn:
            raise ValueError("ISBN 不能为空")

        if not title:
            raise ValueError("书名不能为空")

        book["isbn"] = isbn
        book["title"] = title

        try:
            self.collection.insert_one(book)

        except DuplicateKeyError as exc:
            raise ValueError(
                f"ISBN {isbn} 已存在"
            ) from exc

        self.audit.log_operation(
            operate_type="新增图书",
            target_collection="books",
            target_id=isbn,
            operate_detail=f"新增图书：{title}",
        )

    def update_book(
        self,
        isbn: str,
        changes: dict[str, Any],
    ) -> bool:
        isbn = isbn.strip()

        if not isbn:
            raise ValueError("ISBN 不能为空")

        changes = dict(changes)
        changes.pop("_id", None)

        # ISBN 已被 borrow_logs 作为关联键使用，普通修改不允许改变该字段
        changes.pop("isbn", None)

        if not changes:
            raise ValueError("没有可更新的字段")

        result = self.collection.update_one(
            {
                "isbn": isbn,
            },
            {
                "$set": changes,
            },
        )

        if result.matched_count == 0:
            return False

        self.audit.log_operation(
            operate_type="修改图书",
            target_collection="books",
            target_id=isbn,
            operate_detail=(
                f"修改字段：{', '.join(changes.keys())}"
            ),
        )

        return True

    def delete_book(
        self,
        isbn: str,
    ) -> bool:
        isbn = isbn.strip()

        book = self.collection.find_one(
            {
                "isbn": isbn,
            },
            {
                "_id": 0,
                "title": 1,
            },
        )

        if not book:
            return False

        # 已产生借阅流水的图书继续参与历史统计，不直接删除以免形成孤立记录
        referenced_count = self.borrow_logs.count_documents(
            {
                "book_isbn": isbn,
            }
        )

        if referenced_count > 0:
            raise ValueError(
                f"该图书已有 {referenced_count} 条借阅记录，"
                "不能直接删除"
            )

        result = self.collection.delete_one(
            {
                "isbn": isbn,
            }
        )

        if result.deleted_count != 1:
            return False

        self.audit.log_operation(
            operate_type="删除图书",
            target_collection="books",
            target_id=isbn,
            operate_detail=(
                f"删除图书：{book.get('title', '')}"
            ),
        )

        return True

    def export_books(
        self,
        output_path: str | Path,
    ) -> int:
        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        books = list(
            self.collection.find({})
        )

        # json_util 可以正确序列化 MongoDB 中的 ObjectId 和 Date
        output_path.write_text(
            json_util.dumps(
                books,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.audit.log_operation(
            operate_type="导出图书",
            target_collection="books",
            target_id="ALL",
            operate_detail=(
                f"导出 {len(books)} 条图书记录至 "
                f"{output_path.name}"
            ),
        )

        return len(books)