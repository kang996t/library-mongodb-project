"""图书借阅、归还及借阅记录查询。"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from mongodb_connect import get_db


def _required_text(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name}不能为空。")
    return text


def _display_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return "" if value is None else str(value)


def _print_logs(logs: List[Dict[str, Any]]) -> None:
    if not logs:
        print("未查询到符合条件的借阅记录。")
        return
    for index, log in enumerate(logs, 1):
        print(
            f"{index}. 借阅证号：{log.get('reader_card', '')} | "
            f"图书 ISBN：{log.get('book_isbn', '')} | 状态：{log.get('status', '')}"
        )
        print(
            f"   借阅时间：{_display_datetime(log.get('borrow_date'))} | "
            f"归还时间：{_display_datetime(log.get('return_date'))}"
        )


def insert_one(reader_card: Any, book_isbn: Any):
    """登记一条借阅记录。"""
    card = _required_text(reader_card, "借阅证号")
    isbn = _required_text(book_isbn, "图书 ISBN")
    document = {
        "borrow_date": datetime.now(),
        "reader_card": card,
        "book_isbn": isbn,
        "status": "借出",
    }
    result = get_db()["borrow_logs"].insert_one(document)
    print("新增借阅记录数：1")
    return result


def update_many(reader_card: Any, book_isbn: Any):
    """将指定读者和图书的所有未归还记录标记为已归还。"""
    card = _required_text(reader_card, "借阅证号")
    isbn = _required_text(book_isbn, "图书 ISBN")
    result = get_db()["borrow_logs"].update_many(
        {"reader_card": card, "book_isbn": isbn, "status": "借出"},
        {"$set": {"status": "已归还", "return_date": datetime.now()}},
    )
    print(f"匹配文档数：{result.matched_count}，修改文档数：{result.modified_count}")
    return result


def find(conditions: Optional[Dict[str, Any]] = None, limit: int = 0) -> List[Dict[str, Any]]:
    """查询借阅记录。"""
    if limit < 0:
        raise ValueError("查询数量不能小于 0。")
    cursor = get_db()["borrow_logs"].find(conditions or {}).sort("borrow_date", -1)
    if limit:
        cursor = cursor.limit(limit)
    logs = list(cursor)
    _print_logs(logs)
    return logs


def find_borrowed_records(
    reader_card: Optional[Any] = None, limit: int = 0
) -> List[Dict[str, Any]]:
    """查询当前借出的记录。"""
    conditions: Dict[str, Any] = {"status": "借出"}
    if reader_card is not None and str(reader_card).strip():
        conditions["reader_card"] = str(reader_card).strip()
    return find(conditions, limit)


def find_overdue_records(overdue_days: int = 30) -> List[Dict[str, Any]]:
    """按借出超过指定天数且尚未归还的规则查询逾期记录。"""
    if isinstance(overdue_days, bool) or not isinstance(overdue_days, int) or overdue_days <= 0:
        raise ValueError("逾期天数必须是大于 0 的整数。")
    deadline = datetime.now() - timedelta(days=overdue_days)
    logs = list(
        get_db()["borrow_logs"]
        .find({"status": "借出", "borrow_date": {"$lt": deadline}})
        .sort("borrow_date", 1)
    )
    if not logs:
        print(f"未查询到借出超过 {overdue_days} 天的逾期记录。")
    else:
        print(f"借出超过 {overdue_days} 天的逾期记录：")
        _print_logs(logs)
    return logs
