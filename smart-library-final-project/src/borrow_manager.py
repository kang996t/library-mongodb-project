from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import json_util
from pymongo.database import Database

from audit_manager import AuditManager


class BorrowManager:
    def __init__(
        self,
        db: Database,
        audit_manager: AuditManager,
    ):
        self.books = db["books"]
        self.readers = db["readers"]
        self.borrow_logs = db["borrow_logs"]
        self.audit = audit_manager

    def find_by_reader(
        self,
        card_no: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        card_no = card_no.strip()

        if not card_no:
            raise ValueError("借阅证号不能为空")

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        return list(
            self.borrow_logs.find(
                {
                    "reader_card": card_no,
                },
                {
                    "_id": 0,
                },
            )
            .sort("borrow_date", -1)
            .limit(limit)
        )

    def find_by_book(
        self,
        isbn: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        isbn = isbn.strip()

        if not isbn:
            raise ValueError("ISBN 不能为空")

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        return list(
            self.borrow_logs.find(
                {
                    "book_isbn": isbn,
                },
                {
                    "_id": 0,
                },
            )
            .sort("borrow_date", -1)
            .limit(limit)
        )

    def find_active_by_reader(
        self,
        card_no: str,
    ) -> list[dict[str, Any]]:
        card_no = card_no.strip()

        if not card_no:
            raise ValueError("借阅证号不能为空")

        return list(
            self.borrow_logs.find(
                {
                    "reader_card": card_no,
                    "status": {
                        "$in": ["借出", "逾期"],
                    },
                },
                {
                    "_id": 0,
                },
            ).sort("borrow_date", -1)
        )

    def borrow_book(
        self,
        reader_card: str,
        book_isbn: str,
    ) -> str:
        reader_card = reader_card.strip()
        book_isbn = book_isbn.strip()

        if not reader_card:
            raise ValueError("借阅证号不能为空")

        if not book_isbn:
            raise ValueError("ISBN 不能为空")

        reader = self.readers.find_one(
            {
                "card_no": reader_card,
            },
            {
                "_id": 0,
                "name": 1,
            },
        )

        if not reader:
            raise ValueError(
                f"读者 {reader_card} 不存在"
            )

        book = self.books.find_one(
            {
                "isbn": book_isbn,
            },
            {
                "_id": 0,
                "title": 1,
                "stock": 1,
            },
        )

        if not book:
            raise ValueError(
                f"图书 {book_isbn} 不存在"
            )

        # 通过 stock > 0 的条件更新避免并发情况下库存被减为负数
        stock_result = self.books.update_one(
            {
                "isbn": book_isbn,
                "stock": {
                    "$gt": 0,
                },
            },
            {
                "$inc": {
                    "stock": -1,
                },
            },
        )

        if stock_result.modified_count != 1:
            raise ValueError(
                f"《{book.get('title', '')}》当前无可借库存"
            )

        borrow_document = {
            "borrow_date": datetime.now(timezone.utc),
            "reader_card": reader_card,
            "book_isbn": book_isbn,
            "status": "借出",
        }

        try:
            result = self.borrow_logs.insert_one(
                borrow_document
            )

        except Exception:
            # 单机阶段无法把两个集合放进事务，流水写入失败时恢复库存
            self.books.update_one(
                {
                    "isbn": book_isbn,
                },
                {
                    "$inc": {
                        "stock": 1,
                    },
                },
            )
            raise

        self.audit.log_operation(
            operate_type="新增借阅",
            target_collection="borrow_logs",
            target_id=str(result.inserted_id),
            operate_detail=(
                f"读者 {reader_card} 借阅图书 {book_isbn}"
            ),
        )

        return str(result.inserted_id)

    @staticmethod
    def _to_utc(
        value: datetime,
    ) -> datetime:
        # PyMongo 默认可能返回不带时区信息的 UTC datetime
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    def return_book(
        self,
        reader_card: str,
        book_isbn: str,
    ) -> bool:
        reader_card = reader_card.strip()
        book_isbn = book_isbn.strip()

        loan = self.borrow_logs.find_one(
            {
                "reader_card": reader_card,
                "book_isbn": book_isbn,
                "status": {
                    "$in": ["借出", "逾期"],
                },
            },
            sort=[
                ("borrow_date", -1),
            ],
        )

        if not loan:
            return False

        now = datetime.now(timezone.utc)
        borrow_date = self._to_utc(
            loan["borrow_date"]
        )

        # 当前模型使用整数天保存已完成借阅的实际时长
        duration_days = max(
            (now - borrow_date).days,
            0,
        )

        original_status = loan["status"]

        log_result = self.borrow_logs.update_one(
            {
                "_id": loan["_id"],
                "status": original_status,
            },
            {
                "$set": {
                    "return_date": now,
                    "status": "已归还",
                    "duration_days": duration_days,
                },
            },
        )

        if log_result.modified_count != 1:
            return False

        try:
            stock_result = self.books.update_one(
                {
                    "isbn": book_isbn,
                },
                {
                    "$inc": {
                        "stock": 1,
                    },
                },
            )

            if stock_result.matched_count != 1:
                raise RuntimeError(
                    "借阅记录已更新，但未找到对应图书"
                )

        except Exception:
            # 库存恢复失败时撤销归还状态，避免两个集合状态分裂
            self.borrow_logs.update_one(
                {
                    "_id": loan["_id"],
                },
                {
                    "$set": {
                        "status": original_status,
                    },
                    "$unset": {
                        "return_date": "",
                        "duration_days": "",
                    },
                },
            )
            raise

        self.audit.log_operation(
            operate_type="归还图书",
            target_collection="borrow_logs",
            target_id=str(loan["_id"]),
            operate_detail=(
                f"读者 {reader_card} 归还图书 {book_isbn}"
            ),
        )

        return True

    def export_borrow_logs(
        self,
        output_path: str | Path,
    ) -> int:
        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        records = list(
            self.borrow_logs.find({})
        )

        output_path.write_text(
            json_util.dumps(
                records,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.audit.log_operation(
            operate_type="导出借阅流水",
            target_collection="borrow_logs",
            target_id="ALL",
            operate_detail=(
                f"导出 {len(records)} 条借阅记录至 "
                f"{output_path.name}"
            ),
        )

        return len(records)