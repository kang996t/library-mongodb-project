"""读者信息查询与简单统计。"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from mongodb_connect import get_db


def _display_value(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return "" if value is None else str(value)


def _print_readers(readers: List[Dict[str, Any]]) -> None:
    if not readers:
        print("未查询到符合条件的读者。")
        return
    for index, reader in enumerate(readers, 1):
        print(
            f"{index}. 借阅证号：{_display_value(reader.get('card_no'))} | "
            f"姓名：{_display_value(reader.get('name'))} | "
            f"学院：{_display_value(reader.get('college'))} | "
            f"等级：{_display_value(reader.get('level'))}"
        )
        print(
            f"   邮箱：{_display_value(reader.get('email'))} | "
            f"电话：{_display_value(reader.get('phone'))} | "
            f"注册日期：{_display_value(reader.get('register_date'))} | "
            f"偏好分类：{_display_value(reader.get('fav_categories'))}"
        )


def find(conditions: Optional[Dict[str, Any]] = None, limit: int = 0) -> List[Dict[str, Any]]:
    """按条件查询读者。"""
    if limit < 0:
        raise ValueError("查询数量不能小于 0。")
    cursor = get_db()["readers"].find(conditions or {}).sort("card_no", 1)
    if limit:
        cursor = cursor.limit(limit)
    readers = list(cursor)
    _print_readers(readers)
    return readers


def find_by_card_no(card_no: Any) -> Optional[Dict[str, Any]]:
    """按借阅证号精确查询。"""
    value = str(card_no).strip()
    if not value:
        raise ValueError("借阅证号不能为空。")
    reader = get_db()["readers"].find_one({"card_no": value})
    _print_readers([reader] if reader else [])
    return reader


def show_total_readers() -> int:
    """显示读者总数。"""
    total = get_db()["readers"].count_documents({})
    print(f"读者总数：{total}")
    return total


def list_colleges() -> List[str]:
    """获取学院清单。"""
    colleges = sorted(
        college for college in get_db()["readers"].distinct("college") if college
    )
    if not colleges:
        print("当前没有学院信息。")
    else:
        print("学院清单：" + "、".join(str(college) for college in colleges))
    return colleges


def level_distribution() -> List[Dict[str, Any]]:
    """统计不同借阅等级人数。"""
    pipeline = [
        {"$group": {"_id": {"$ifNull": ["$level", "未设置"]}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
    ]
    rows = list(get_db()["readers"].aggregate(pipeline))
    if not rows:
        print("当前没有读者等级统计数据。")
    else:
        print("读者等级分布：")
        for row in rows:
            print(f"- {row['_id']}：{row['count']} 人")
    return rows


def college_distribution() -> List[Dict[str, Any]]:
    """按学院统计读者人数。"""
    pipeline = [
        {"$group": {"_id": {"$ifNull": ["$college", "未设置"]}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
    ]
    rows = list(get_db()["readers"].aggregate(pipeline))
    if not rows:
        print("当前没有学院统计数据。")
    else:
        print("学院读者人数：")
        for row in rows:
            print(f"- {row['_id']}：{row['count']} 人")
    return rows
