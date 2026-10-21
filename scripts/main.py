"""图书情报检索与统计平台命令行入口。"""

from typing import Callable, Dict

import book_manager
import borrow_manager
import reader_manager
import stat_manager
from mongodb_connect import close_client, get_db, test_connection


MENU = """
========== 图书情报检索与统计平台 ==========
1. 按 ISBN 查询图书
2. 按最低价格查询图书
3. 图书评分 Top 5
4. 修改图书库存
5. 删除指定图书
6. 查询读者信息
7. 读者学院统计
8. 读者等级分布
9. 借阅登记
10. 图书归还
11. 查询逾期记录
12. 图书分类统计
13. 年度借阅趋势
14. 畅销图书排行
0. 退出
==========================================
"""


def _show_collection_counts() -> None:
    db = get_db()
    print("当前集合文档总数：")
    for collection_name in ("books", "readers", "borrow_logs", "category_stats"):
        count = db[collection_name].count_documents({})
        print(f"- {collection_name}：{count}")


def _read_nonempty(prompt: str) -> str:
    value = input(prompt).strip()
    if not value:
        raise ValueError("输入不能为空。")
    return value


def _query_book_by_isbn() -> None:
    book_manager.find_one(_read_nonempty("请输入 ISBN："))


def _query_book_by_price() -> None:
    book_manager.find_by_min_price(_read_nonempty("请输入最低价格："))


def _show_rating_top_five() -> None:
    book_manager.rating_ranking(5)


def _update_book_stock() -> None:
    isbn = _read_nonempty("请输入 ISBN：")
    stock = _read_nonempty("请输入新库存：")
    book_manager.update_one(isbn, stock)


def _delete_book() -> None:
    isbn = _read_nonempty("请输入要删除的图书 ISBN：")
    confirmation = input("此操作将删除该图书，输入 Y 确认：").strip().upper()
    if confirmation != "Y":
        print("已取消删除。")
        return
    book_manager.delete_one(isbn)


def _query_readers() -> None:
    print("可按借阅证号精确查询；直接回车可按其他条件查询。")
    card_no = input("借阅证号：").strip()
    if card_no:
        reader_manager.find_by_card_no(card_no)
        return

    name = input("姓名（支持部分匹配，直接回车忽略）：").strip()
    college = input("学院（精确匹配，直接回车忽略）：").strip()
    conditions = {}
    if name:
        conditions["name"] = {"$regex": name, "$options": "i"}
    if college:
        conditions["college"] = college
    reader_manager.find(conditions, limit=50)


def _register_borrow() -> None:
    card_no = _read_nonempty("请输入借阅证号：")
    isbn = _read_nonempty("请输入图书 ISBN：")
    borrow_manager.insert_one(card_no, isbn)


def _return_book() -> None:
    card_no = _read_nonempty("请输入借阅证号：")
    isbn = _read_nonempty("请输入图书 ISBN：")
    borrow_manager.update_many(card_no, isbn)


def _query_overdue() -> None:
    days_text = input("请输入逾期天数（直接回车使用 30 天）：").strip()
    if not days_text:
        days = 30
    else:
        try:
            days = int(days_text)
        except ValueError as exc:
            raise ValueError("逾期天数必须是整数。") from exc
    borrow_manager.find_overdue_records(days)


def _run_menu() -> None:
    actions: Dict[str, Callable[[], None]] = {
        "1": _query_book_by_isbn,
        "2": _query_book_by_price,
        "3": _show_rating_top_five,
        "4": _update_book_stock,
        "5": _delete_book,
        "6": _query_readers,
        "7": reader_manager.college_distribution,
        "8": reader_manager.level_distribution,
        "9": _register_borrow,
        "10": _return_book,
        "11": _query_overdue,
        "12": stat_manager.category_statistics,
        "13": stat_manager.annual_borrow_trend,
        "14": lambda: stat_manager.bestseller_ranking(5),
    }

    while True:
        print(MENU)
        choice = input("请选择功能：").strip()
        if choice == "0":
            print("已退出系统。")
            break
        action = actions.get(choice)
        if action is None:
            print("输入无效，请输入菜单中的编号。")
            continue
        try:
            action()
        except (ValueError, TypeError) as exc:
            print(f"输入错误：{exc}")
        except Exception as exc:
            print(f"操作失败：{exc}")


def main() -> None:
    try:
        connected, message = test_connection()
        print(message)
        if not connected:
            return
        _show_collection_counts()
        _run_menu()
    except KeyboardInterrupt:
        print("\n操作已中断，程序退出。")
    except Exception as exc:
        print(f"程序启动失败：{exc}")
    finally:
        close_client()


if __name__ == "__main__":
    main()
