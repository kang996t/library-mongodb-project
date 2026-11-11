from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from audit_manager import AuditManager


class StatManager:
    def __init__(
        self,
        db: Database,
        audit_manager: AuditManager,
    ):
        self.books = db["books"]
        self.readers = db["readers"]
        self.borrow_logs = db["borrow_logs"]
        self.stat_result = db["stat_result"]
        self.audit = audit_manager

    def category_statistics(
        self,
    ) -> list[dict[str, Any]]:
        """按类别统计藏书量、平均价格和平均评分。"""

        pipeline = [
            {
                "$group": {
                    "_id": "$category",
                    "book_count": {"$sum": 1},
                    "avg_price": {"$avg": "$price"},
                    "avg_rating": {"$avg": "$rating"},
                }
            },
            {
                # 将分组键恢复为 category，并统一保留两位小数
                "$project": {
                    "_id": 0,
                    "category": "$_id",
                    "book_count": 1,
                    "avg_price": {
                        "$round": ["$avg_price", 2]
                    },
                    "avg_rating": {
                        "$round": ["$avg_rating", 2]
                    },
                }
            },
            {
                "$sort": {
                    "category": 1
                }
            },
        ]

        return list(
            self.books.aggregate(pipeline)
        )

    def college_borrow_top(
        self,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """统计各学院借阅总量，并返回借阅量最高的若干学院。"""

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        pipeline = [
            {
                # 借阅流水只保存借阅证号，需要关联 readers 获取学院信息
                "$lookup": {
                    "from": "readers",
                    "localField": "reader_card",
                    "foreignField": "card_no",
                    "as": "reader",
                }
            },
            {
                "$unwind": "$reader"
            },
            {
                "$group": {
                    "_id": "$reader.college",
                    "borrow_count": {"$sum": 1},
                }
            },
            {
                # 借阅量相同时按学院名称排序，使结果顺序稳定
                "$sort": {
                    "borrow_count": -1,
                    "_id": 1,
                }
            },
            {
                "$limit": limit
            },
            {
                "$project": {
                    "_id": 0,
                    "college": "$_id",
                    "borrow_count": 1,
                }
            },
        ]

        return list(
            self.borrow_logs.aggregate(pipeline)
        )

    def monthly_borrow_trend(
        self,
    ) -> list[dict[str, Any]]:
        """按年月统计借阅次数。"""

        pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m",
                            "date": "$borrow_date",

                            # MongoDB 内部按 UTC 保存时间，
                            # 统计月份时统一按北京时间划分
                            "timezone": "Asia/Shanghai",
                        }
                    },
                    "borrow_count": {"$sum": 1},
                }
            },
            {
                "$sort": {
                    "_id": 1
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "month": "$_id",
                    "borrow_count": 1,
                }
            },
        ]

        return list(
            self.borrow_logs.aggregate(pipeline)
        )

    def popular_books(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """统计借阅次数最多的图书，并返回对应馆藏位置。"""

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        pipeline = [
            {
                # 热门程度以 borrow_logs 中真实出现的借阅次数为统计口径
                "$group": {
                    "_id": "$book_isbn",
                    "borrow_count": {"$sum": 1},
                }
            },
            {
                "$sort": {
                    "borrow_count": -1,
                    "_id": 1,
                }
            },
            {
                "$limit": limit
            },
            {
                # 通过 ISBN 关联 books，取得书名及 location 嵌套字段
                "$lookup": {
                    "from": "books",
                    "localField": "_id",
                    "foreignField": "isbn",
                    "as": "book",
                }
            },
            {
                "$unwind": "$book"
            },
            {
                "$project": {
                    "_id": 0,
                    "isbn": "$_id",
                    "title": "$book.title",
                    "borrow_count": 1,
                    "location": "$book.location",
                }
            },
        ]

        return list(
            self.borrow_logs.aggregate(pipeline)
        )

    def refresh_category_statistics(
        self,
    ) -> int:
        """
        重新计算分类统计，并更新 stat_result 中的持久化结果。
        """

        statistics = self.category_statistics()
        generated_at = datetime.now(timezone.utc)

        for item in statistics:
            # category 作为稳定业务标识，使用 upsert 防止重复运行产生重复记录
            self.stat_result.update_one(
                {
                    "category": item["category"]
                },
                {
                    "$set": {
                        "category": item["category"],
                        "book_count": item["book_count"],
                        "avg_price": item["avg_price"],
                        "avg_rating": item["avg_rating"],
                        "generated_at": generated_at,
                    }
                },
                upsert=True,
            )

        # 刷新统计结果属于数据库写操作，需要进入审计日志
        self.audit.log_operation(
            operate_type="刷新分类统计",
            target_collection="stat_result",
            target_id="ALL",
            operate_detail=(
                f"更新 {len(statistics)} 条分类统计结果"
            ),
        )

        return len(statistics)

    def get_saved_category_statistics(
        self,
    ) -> list[dict[str, Any]]:
        """读取 stat_result 中已经持久化的分类统计结果。"""

        return list(
            self.stat_result.find(
                {},
                {
                    "_id": 0,
                    "category": 1,
                    "book_count": 1,
                    "avg_price": 1,
                    "avg_rating": 1,
                    "generated_at": 1,
                },
            ).sort("category", 1)
        )