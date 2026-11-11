"""基于聚合管道的图书与借阅统计。"""

from typing import Any, Dict, List

from mongodb_connect import get_db


def category_statistics() -> List[Dict[str, Any]]:
    """按分类统计库存、平均价格和图书数量。"""
    pipeline = [
        {
            "$group": {
                "_id": {"$ifNull": ["$category", "未分类"]},
                "total_stock": {"$sum": {"$ifNull": ["$stock", 0]}},
                "average_price": {"$avg": "$price"},
                "book_count": {"$sum": 1},
            }
        },
        {"$sort": {"total_stock": -1, "_id": 1}},
    ]
    rows = list(get_db()["books"].aggregate(pipeline))
    if not rows:
        print("当前没有图书分类统计数据。")
    else:
        print("图书分类统计：")
        for row in rows:
            average = row.get("average_price")
            average_text = f"{average:.2f}" if isinstance(average, (int, float)) else "无"
            print(
                f"- {row['_id']}：库存总量 {row['total_stock']}，"
                f"平均价格 {average_text}，图书数量 {row['book_count']}"
            )
    return rows


def annual_borrow_trend() -> List[Dict[str, Any]]:
    """按借阅日期年份统计借阅量。"""
    pipeline = [
        {"$match": {"borrow_date": {"$type": "date"}}},
        {"$group": {"_id": {"$year": "$borrow_date"}, "borrow_count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    rows = list(get_db()["borrow_logs"].aggregate(pipeline))
    if not rows:
        print("当前没有年度借阅趋势数据。")
    else:
        print("年度借阅趋势：")
        for row in rows:
            print(f"- {row['_id']}年：{row['borrow_count']} 次")
    return rows


def bestseller_ranking(limit: int = 5) -> List[Dict[str, Any]]:
    """按 borrow_count 生成畅销图书排行。"""
    if limit <= 0:
        raise ValueError("排行榜数量必须大于 0。")
    pipeline = [
        {"$sort": {"borrow_count": -1, "isbn": 1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "isbn": 1, "title": 1, "borrow_count": 1}},
    ]
    rows = list(get_db()["books"].aggregate(pipeline))
    if not rows:
        print("当前没有畅销图书排行数据。")
    else:
        print(f"畅销图书 Top {limit}：")
        for index, row in enumerate(rows, 1):
            print(
                f"{index}. ISBN：{row.get('isbn', '')} | "
                f"书名：{row.get('title', '')} | "
                f"借阅次数：{row.get('borrow_count', 0)}"
            )
    return rows
