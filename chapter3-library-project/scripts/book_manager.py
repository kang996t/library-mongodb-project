"""图书信息的新增、查询、修改和删除。"""

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from mongodb_connect import get_db


def _validate_isbn(isbn: Any) -> str:
    value = str(isbn).strip()
    compact = value.replace("-", "").replace(" ", "")
    if len(compact) not in (10, 13):
        raise ValueError("ISBN 应为 10 位或 13 位。")
    if not compact[:-1].isdigit() or not (compact[-1].isdigit() or compact[-1].upper() == "X"):
        raise ValueError("ISBN 格式不正确。")
    return value


def _validate_price(price: Any) -> float:
    if isinstance(price, bool):
        raise ValueError("价格必须是非负数字。")
    try:
        value = float(price)
    except (TypeError, ValueError) as exc:
        raise ValueError("价格必须是非负数字。") from exc
    if value < 0:
        raise ValueError("价格不能小于 0。")
    return value


def _validate_stock(stock: Any) -> int:
    if isinstance(stock, bool):
        raise ValueError("库存必须是非负整数。")
    try:
        value = int(stock)
    except (TypeError, ValueError) as exc:
        raise ValueError("库存必须是非负整数。") from exc
    if str(stock).strip() not in (str(value), f"+{value}") or value < 0:
        raise ValueError("库存必须是非负整数。")
    return value


def _prepare_book(book: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(book, dict):
        raise ValueError("图书数据必须是字典。")
    data = dict(book)
    data["isbn"] = _validate_isbn(data.get("isbn", ""))
    if not str(data.get("title", "")).strip():
        raise ValueError("书名不能为空。")
    data["title"] = str(data["title"]).strip()
    if "price" in data:
        data["price"] = _validate_price(data["price"])
    if "stock" in data:
        data["stock"] = _validate_stock(data["stock"])
    return data


def _display_value(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return "" if value is None else str(value)


def _print_books(books: List[Dict[str, Any]]) -> None:
    if not books:
        print("未查询到符合条件的图书。")
        return
    for index, book in enumerate(books, 1):
        print(
            f"{index}. ISBN：{_display_value(book.get('isbn'))} | "
            f"书名：{_display_value(book.get('title'))} | "
            f"作者：{_display_value(book.get('author'))} | "
            f"出版社：{_display_value(book.get('publisher'))}"
        )
        print(
            f"   分类：{_display_value(book.get('category'))} | "
            f"价格：{_display_value(book.get('price'))} | "
            f"库存：{_display_value(book.get('stock'))} | "
            f"评分：{_display_value(book.get('rating'))} | "
            f"借阅次数：{_display_value(book.get('borrow_count'))}"
        )
        if book.get("tags") or book.get("publish_date"):
            print(
                f"   标签：{_display_value(book.get('tags'))} | "
                f"出版日期：{_display_value(book.get('publish_date'))}"
            )


def insert_one(book: Dict[str, Any]):
    """新增一本图书。"""
    data = _prepare_book(book)
    result = get_db()["books"].insert_one(data)
    print("新增文档数：1")
    return result


def insert_many(books: Iterable[Dict[str, Any]]):
    """批量新增图书，写入前先完成全部基础校验。"""
    data = [_prepare_book(book) for book in books]
    if not data:
        raise ValueError("批量新增的数据不能为空。")
    isbn_list = [book["isbn"] for book in data]
    if len(isbn_list) != len(set(isbn_list)):
        raise ValueError("批量数据中存在重复 ISBN。")
    result = get_db()["books"].insert_many(data)
    print(f"新增文档数：{len(result.inserted_ids)}")
    return result


def find_one(isbn: Any) -> Optional[Dict[str, Any]]:
    """按 ISBN 精确查询。"""
    isbn_value = _validate_isbn(isbn)
    book = get_db()["books"].find_one({"isbn": isbn_value})
    _print_books([book] if book else [])
    return book


def find(conditions: Optional[Dict[str, Any]] = None, limit: int = 0) -> List[Dict[str, Any]]:
    """按 MongoDB 条件检索图书。"""
    if limit < 0:
        raise ValueError("查询数量不能小于 0。")
    cursor = get_db()["books"].find(conditions or {}).sort("isbn", 1)
    if limit:
        cursor = cursor.limit(limit)
    books = list(cursor)
    _print_books(books)
    return books


def find_by_min_price(min_price: Any) -> List[Dict[str, Any]]:
    """查询价格不低于指定值的图书。"""
    price = _validate_price(min_price)
    books = list(get_db()["books"].find({"price": {"$gte": price}}).sort("price", 1))
    _print_books(books)
    return books


def rating_ranking(limit: int = 5) -> List[Dict[str, Any]]:
    """显示评分排行榜。"""
    if limit <= 0:
        raise ValueError("排行榜数量必须大于 0。")
    books = list(
        get_db()["books"]
        .find({"rating": {"$ne": None}})
        .sort([("rating", -1), ("borrow_count", -1)])
        .limit(limit)
    )
    _print_books(books)
    return books


def update_one(isbn: Any, new_stock: Any):
    """按 ISBN 修改库存。"""
    isbn_value = _validate_isbn(isbn)
    stock = _validate_stock(new_stock)
    result = get_db()["books"].update_one(
        {"isbn": isbn_value}, {"$set": {"stock": stock}}
    )
    print(f"匹配文档数：{result.matched_count}，修改文档数：{result.modified_count}")
    return result


def delete_one(isbn: Any):
    """按 ISBN 删除一本图书。"""
    isbn_value = _validate_isbn(isbn)
    result = get_db()["books"].delete_one({"isbn": isbn_value})
    print(f"删除文档数：{result.deleted_count}")
    return result


def delete_many(conditions: Dict[str, Any]):
    """按明确条件批量删除图书，不允许空条件。"""
    if not isinstance(conditions, dict) or not conditions:
        raise ValueError("批量删除条件不能为空。")
    result = get_db()["books"].delete_many(conditions)
    print(f"删除文档数：{result.deleted_count}")
    return result
