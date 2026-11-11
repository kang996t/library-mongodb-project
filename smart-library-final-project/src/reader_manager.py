from __future__ import annotations

from pathlib import Path
from typing import Any

from bson import json_util
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from audit_manager import AuditManager


class ReaderManager:
    def __init__(
        self,
        db: Database,
        audit_manager: AuditManager,
    ):
        self.collection = db["readers"]
        self.borrow_logs = db["borrow_logs"]
        self.audit = audit_manager

    def get_by_card_no(
        self,
        card_no: str,
    ) -> dict[str, Any] | None:
        return self.collection.find_one(
            {
                "card_no": card_no.strip(),
            },
            {
                "_id": 0,
            },
        )

    def search_by_college(
        self,
        college: str,
    ) -> list[dict[str, Any]]:
        college = college.strip()

        if not college:
            raise ValueError("学院名称不能为空")

        return list(
            self.collection.find(
                {
                    "college": college,
                },
                {
                    "_id": 0,
                },
            ).sort("card_no", 1)
        )

    def list_readers(
        self,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        return list(
            self.collection.find(
                {},
                {
                    "_id": 0,
                },
            )
            .sort("card_no", 1)
            .limit(limit)
        )

    def add_reader(
        self,
        reader: dict[str, Any],
    ) -> None:
        card_no = str(
            reader.get("card_no", "")
        ).strip()

        name = str(
            reader.get("name", "")
        ).strip()

        if not card_no:
            raise ValueError("借阅证号不能为空")

        if not name:
            raise ValueError("读者姓名不能为空")

        reader["card_no"] = card_no
        reader["name"] = name

        try:
            self.collection.insert_one(reader)

        except DuplicateKeyError as exc:
            raise ValueError(
                f"借阅证号 {card_no} 已存在"
            ) from exc

        self.audit.log_operation(
            operate_type="新增读者",
            target_collection="readers",
            target_id=card_no,
            operate_detail=f"新增读者：{name}",
        )

    def update_reader(
        self,
        card_no: str,
        changes: dict[str, Any],
    ) -> bool:
        card_no = card_no.strip()

        if not card_no:
            raise ValueError("借阅证号不能为空")

        changes = dict(changes)
        changes.pop("_id", None)

        # card_no 已被 borrow_logs 引用，普通修改操作不允许改变关联键
        changes.pop("card_no", None)

        if not changes:
            raise ValueError("没有可更新的字段")

        result = self.collection.update_one(
            {
                "card_no": card_no,
            },
            {
                "$set": changes,
            },
        )

        if result.matched_count == 0:
            return False

        self.audit.log_operation(
            operate_type="修改读者",
            target_collection="readers",
            target_id=card_no,
            operate_detail=(
                f"修改字段：{', '.join(changes.keys())}"
            ),
        )

        return True

    def delete_reader(
        self,
        card_no: str,
    ) -> bool:
        card_no = card_no.strip()

        reader = self.collection.find_one(
            {
                "card_no": card_no,
            },
            {
                "_id": 0,
                "name": 1,
            },
        )

        if not reader:
            return False

        # 历史流水仍需用于统计分析，存在关联记录时不直接删除读者
        referenced_count = self.borrow_logs.count_documents(
            {
                "reader_card": card_no,
            }
        )

        if referenced_count > 0:
            raise ValueError(
                f"该读者已有 {referenced_count} 条借阅记录，"
                "不能直接删除"
            )

        result = self.collection.delete_one(
            {
                "card_no": card_no,
            }
        )

        if result.deleted_count != 1:
            return False

        self.audit.log_operation(
            operate_type="删除读者",
            target_collection="readers",
            target_id=card_no,
            operate_detail=(
                f"删除读者：{reader.get('name', '')}"
            ),
        )

        return True

    def export_readers(
        self,
        output_path: str | Path,
    ) -> int:
        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        readers = list(
            self.collection.find({})
        )

        output_path.write_text(
            json_util.dumps(
                readers,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.audit.log_operation(
            operate_type="导出读者",
            target_collection="readers",
            target_id="ALL",
            operate_detail=(
                f"导出 {len(readers)} 条读者记录至 "
                f"{output_path.name}"
            ),
        )

        return len(readers)