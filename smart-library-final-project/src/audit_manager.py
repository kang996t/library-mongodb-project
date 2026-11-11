from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database


class AuditManager:
    def __init__(self, db: Database):
        self.collection = db["audit_logs"]
        self.operator = os.getenv(
            "MONGODB_APP_USER",
            "unknown",
        )

    def log_operation(
        self,
        operate_type: str,
        target_collection: str,
        target_id: str,
        operate_detail: str,
        client_ip: str | None = None,
    ) -> None:
        # 本地命令行程序无法稳定取得真实客户端 IP，因此该字段允许为空
        document = {
            "operate_time": datetime.now(timezone.utc),
            "operator": self.operator,
            "operate_type": operate_type,
            "target_collection": target_collection,
            "target_id": str(target_id),
            "operate_detail": operate_detail,
            "client_ip": client_ip,
        }

        self.collection.insert_one(document)

    def recent_operations(
        self,
        limit: int = 100,
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
            .sort("operate_time", -1)
            .limit(limit)
        )