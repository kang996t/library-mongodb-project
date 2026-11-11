from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from pprint import pprint
from typing import Any

from pymongo.errors import PyMongoError

from audit_manager import AuditManager
from book_manager import BookManager
from borrow_manager import BorrowManager
from gridfs_manager import GridFSManager
from mongodb_connect import (
    check_connection,
    create_client,
    get_database,
)
from reader_manager import ReaderManager
from stat_manager import StatManager


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def print_records(
    records: list[dict[str, Any]],
) -> None:
    """统一展示查询和统计结果。"""
    if not records:
        print("未查询到符合条件的记录。")
        return

    print(f"\n共 {len(records)} 条结果：\n")

    for index, record in enumerate(
        records,
        start=1,
    ):
        print(f"[{index}]")
        pprint(
            record,
            sort_dicts=False,
        )
        print()


def input_float(
    prompt: str,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    while True:
        try:
            value = float(
                input(prompt).strip()
            )

            if (
                min_value is not None
                and value < min_value
            ):
                print(
                    f"输入值不能小于 {min_value}。"
                )
                continue

            if (
                max_value is not None
                and value > max_value
            ):
                print(
                    f"输入值不能大于 {max_value}。"
                )
                continue

            return value

        except ValueError:
            print("请输入有效数字。")


def input_int(
    prompt: str,
    min_value: int | None = None,
) -> int:
    while True:
        try:
            value = int(
                input(prompt).strip()
            )

            if (
                min_value is not None
                and value < min_value
            ):
                print(
                    f"输入值不能小于 {min_value}。"
                )
                continue

            return value

        except ValueError:
            print("请输入有效整数。")


def input_date(
    prompt: str,
) -> datetime:
    """按北京时间解析日期，随后由 PyMongo 写入 BSON Date。"""
    while True:
        value = input(prompt).strip()

        try:
            parsed = datetime.strptime(
                value,
                "%Y-%m-%d",
            )

            return parsed.replace(
                tzinfo=timezone(
                    timedelta(hours=8)
                )
            )

        except ValueError:
            print(
                "日期格式应为 YYYY-MM-DD，"
                "例如 2025-06-01。"
            )


def pause() -> None:
    input("\n按 Enter 返回...")


def book_search_menu(
    book_manager: BookManager,
) -> None:
    while True:
        print(
            """
图书检索
1. 类别与价格区间组合筛选
2. 标签多选匹配
3. 书名模糊检索
4. 出版年份范围检索
5. 查询缺少 tags 字段的图书
6. 评分 Top 10
0. 返回主菜单
"""
        )

        choice = input("请选择：").strip()

        try:
            if choice == "1":
                category = input(
                    "图书类别："
                ).strip()

                min_price = input_float(
                    "最低价格：",
                    min_value=0,
                )

                max_price = input_float(
                    "最高价格：",
                    min_value=0,
                )

                records = (
                    book_manager
                    .search_by_category_price(
                        category,
                        min_price,
                        max_price,
                    )
                )

                print_records(records)

            elif choice == "2":
                raw_tags = input(
                    "多个标签用英文逗号分隔："
                )

                records = (
                    book_manager.search_by_tags(
                        raw_tags.split(",")
                    )
                )

                print_records(records)

            elif choice == "3":
                keyword = input(
                    "书名关键词："
                )

                records = (
                    book_manager.search_by_title(
                        keyword
                    )
                )

                print_records(records)

            elif choice == "4":
                start_year = input_int(
                    "起始年份：",
                    min_value=1,
                )

                end_year = input_int(
                    "结束年份：",
                    min_value=1,
                )

                records = (
                    book_manager
                    .search_by_publish_year(
                        start_year,
                        end_year,
                    )
                )

                print_records(records)

            elif choice == "5":
                records = (
                    book_manager
                    .find_missing_tags()
                )

                print_records(records)

            elif choice == "6":
                records = (
                    book_manager.top_rated(10)
                )

                print_records(records)

            elif choice == "0":
                return

            else:
                print("无效选项。")
                continue

        except (
            ValueError,
            PyMongoError,
        ) as exc:
            print(f"操作失败：{exc}")

        pause()


def build_book_from_input() -> dict[str, Any]:
    """按照当前 books 数据模型录入一条图书记录。"""
    isbn = input("ISBN：").strip()
    title = input("书名：").strip()
    author = input("作者：").strip()
    publisher = input("出版社：").strip()
    category = input("类别：").strip()

    price = input_float(
        "价格：",
        min_value=0,
    )

    rating = input_float(
        "评分：",
        min_value=0,
        max_value=5,
    )

    stock = input_int(
        "库存：",
        min_value=0,
    )

    borrow_count = input_int(
        "历史借阅次数：",
        min_value=0,
    )

    publish_date = input_date(
        "出版日期 YYYY-MM-DD："
    )

    floor = input(
        "楼层区域："
    ).strip()

    shelf = input(
        "架位号："
    ).strip()

    copies = input_int(
        "复本数：",
        min_value=0,
    )

    book: dict[str, Any] = {
        "isbn": isbn,
        "title": title,
        "author": author,
        "publisher": publisher,
        "category": category,
        "price": price,
        "rating": rating,
        "stock": stock,
        "publish_date": publish_date,
        "borrow_count": borrow_count,
        "location": {
            "floor": floor,
            "shelf": shelf,
            "copies": copies,
        },
    }

    tags_text = input(
        "标签，多个标签用英文逗号分隔，可留空："
    ).strip()

    if tags_text:
        book["tags"] = [
            tag.strip()
            for tag in tags_text.split(",")
            if tag.strip()
        ]

    ebook_name = input(
        "电子书文件名，可留空："
    ).strip()

    if ebook_name:
        book["ebook_name"] = ebook_name

    return book


def book_manage_menu(
    book_manager: BookManager,
) -> None:
    while True:
        print(
            """
图书信息管理
1. 按 ISBN 查询
2. 新增图书
3. 修改图书
4. 删除图书
5. 导出全部图书
0. 返回主菜单
"""
        )

        choice = input("请选择：").strip()

        try:
            if choice == "1":
                isbn = input(
                    "ISBN："
                ).strip()

                record = (
                    book_manager.get_by_isbn(
                        isbn
                    )
                )

                if record:
                    pprint(
                        record,
                        sort_dicts=False,
                    )
                else:
                    print("未找到该图书。")

            elif choice == "2":
                book = build_book_from_input()

                book_manager.add_book(book)

                print("图书新增成功。")

            elif choice == "3":
                isbn = input(
                    "ISBN："
                ).strip()

                print(
                    "可修改字段：title、author、publisher、"
                    "category、price、rating、stock"
                )

                field = input(
                    "字段名："
                ).strip()

                allowed_fields = {
                    "title",
                    "author",
                    "publisher",
                    "category",
                    "price",
                    "rating",
                    "stock",
                }

                if field not in allowed_fields:
                    print("不支持修改该字段。")
                    pause()
                    continue

                raw_value = input(
                    "新值："
                ).strip()

                if field in {
                    "price",
                    "rating",
                }:
                    value: Any = float(
                        raw_value
                    )

                elif field == "stock":
                    value = int(
                        raw_value
                    )

                    if value < 0:
                        raise ValueError(
                            "库存不能为负数"
                        )

                else:
                    value = raw_value

                updated = (
                    book_manager.update_book(
                        isbn,
                        {
                            field: value,
                        },
                    )
                )

                print(
                    "修改成功。"
                    if updated
                    else "未找到该图书。"
                )

            elif choice == "4":
                isbn = input(
                    "ISBN："
                ).strip()

                deleted = (
                    book_manager.delete_book(
                        isbn
                    )
                )

                print(
                    "删除成功。"
                    if deleted
                    else "未找到该图书。"
                )

            elif choice == "5":
                output_path = (
                    OUTPUT_DIR
                    / "books_export.json"
                )

                count = (
                    book_manager.export_books(
                        output_path
                    )
                )

                print(
                    f"已导出 {count} 条图书记录："
                    f"{output_path}"
                )

            elif choice == "0":
                return

            else:
                print("无效选项。")
                continue

        except (
            ValueError,
            PyMongoError,
        ) as exc:
            print(f"操作失败：{exc}")

        pause()


def build_reader_from_input() -> dict[str, Any]:
    """按照当前 readers 数据模型录入一条读者记录。"""
    card_no = input(
        "借阅证号："
    ).strip()

    name = input(
        "姓名："
    ).strip()

    college = input(
        "学院："
    ).strip()

    phone = input(
        "联系电话："
    ).strip()

    while True:
        level = input(
            "读者等级（普通/高级/教师）："
        ).strip()

        if level in {
            "普通",
            "高级",
            "教师",
        }:
            break

        print(
            "读者等级只能为普通、高级或教师。"
        )

    register_date = input_date(
        "注册日期 YYYY-MM-DD："
    )

    email = input(
        "邮箱，可留空："
    ).strip()

    reader: dict[str, Any] = {
        "card_no": card_no,
        "name": name,
        "college": college,
        "phone": phone,
        "level": level,
        "register_date": register_date,
        "email": (
            email
            if email
            else None
        ),
    }

    fav_text = input(
        "偏好类别，多个类别用英文逗号分隔，可留空："
    ).strip()

    if fav_text:
        reader["fav_categories"] = [
            item.strip()
            for item in fav_text.split(",")
            if item.strip()
        ]

    return reader


def reader_manage_menu(
    reader_manager: ReaderManager,
) -> None:
    while True:
        print(
            """
读者信息管理
1. 按借阅证号查询
2. 按学院查询
3. 查看读者列表
4. 新增读者
5. 修改读者
6. 删除读者
7. 导出全部读者
0. 返回主菜单
"""
        )

        choice = input("请选择：").strip()

        try:
            if choice == "1":
                card_no = input(
                    "借阅证号："
                ).strip()

                record = (
                    reader_manager
                    .get_by_card_no(card_no)
                )

                if record:
                    pprint(
                        record,
                        sort_dicts=False,
                    )
                else:
                    print("未找到该读者。")

            elif choice == "2":
                college = input(
                    "学院："
                )

                records = (
                    reader_manager
                    .search_by_college(
                        college
                    )
                )

                print_records(records)

            elif choice == "3":
                records = (
                    reader_manager
                    .list_readers()
                )

                print_records(records)

            elif choice == "4":
                reader = (
                    build_reader_from_input()
                )

                reader_manager.add_reader(
                    reader
                )

                print("读者新增成功。")

            elif choice == "5":
                card_no = input(
                    "借阅证号："
                ).strip()

                print(
                    "可修改字段：name、college、email、"
                    "phone、level"
                )

                field = input(
                    "字段名："
                ).strip()

                allowed_fields = {
                    "name",
                    "college",
                    "email",
                    "phone",
                    "level",
                }

                if field not in allowed_fields:
                    print("不支持修改该字段。")
                    pause()
                    continue

                value = input(
                    "新值："
                ).strip()

                if (
                    field == "level"
                    and value not in {
                        "普通",
                        "高级",
                        "教师",
                    }
                ):
                    raise ValueError(
                        "读者等级只能为普通、高级或教师"
                    )

                if (
                    field == "email"
                    and not value
                ):
                    value = None

                updated = (
                    reader_manager
                    .update_reader(
                        card_no,
                        {
                            field: value,
                        },
                    )
                )

                print(
                    "修改成功。"
                    if updated
                    else "未找到该读者。"
                )

            elif choice == "6":
                card_no = input(
                    "借阅证号："
                ).strip()

                deleted = (
                    reader_manager
                    .delete_reader(card_no)
                )

                print(
                    "删除成功。"
                    if deleted
                    else "未找到该读者。"
                )

            elif choice == "7":
                output_path = (
                    OUTPUT_DIR
                    / "readers_export.json"
                )

                count = (
                    reader_manager
                    .export_readers(
                        output_path
                    )
                )

                print(
                    f"已导出 {count} 条读者记录："
                    f"{output_path}"
                )

            elif choice == "0":
                return

            else:
                print("无效选项。")
                continue

        except (
            ValueError,
            PyMongoError,
        ) as exc:
            print(f"操作失败：{exc}")

        pause()


def borrow_manage_menu(
    borrow_manager: BorrowManager,
) -> None:
    while True:
        print(
            """
借阅记录管理
1. 按读者查询借阅记录
2. 按图书查询借阅记录
3. 查询读者未完成借阅
4. 办理借书
5. 办理归还
6. 导出全部借阅流水
0. 返回主菜单
"""
        )

        choice = input("请选择：").strip()

        try:
            if choice == "1":
                card_no = input(
                    "借阅证号："
                )

                records = (
                    borrow_manager
                    .find_by_reader(card_no)
                )

                print_records(records)

            elif choice == "2":
                isbn = input(
                    "ISBN："
                )

                records = (
                    borrow_manager
                    .find_by_book(isbn)
                )

                print_records(records)

            elif choice == "3":
                card_no = input(
                    "借阅证号："
                )

                records = (
                    borrow_manager
                    .find_active_by_reader(
                        card_no
                    )
                )

                print_records(records)

            elif choice == "4":
                card_no = input(
                    "借阅证号："
                )

                isbn = input(
                    "ISBN："
                )

                record_id = (
                    borrow_manager
                    .borrow_book(
                        card_no,
                        isbn,
                    )
                )

                print(
                    f"借阅成功，流水 ID："
                    f"{record_id}"
                )

            elif choice == "5":
                card_no = input(
                    "借阅证号："
                )

                isbn = input(
                    "ISBN："
                )

                returned = (
                    borrow_manager
                    .return_book(
                        card_no,
                        isbn,
                    )
                )

                print(
                    "归还成功。"
                    if returned
                    else "未找到对应的未完成借阅记录。"
                )

            elif choice == "6":
                output_path = (
                    OUTPUT_DIR
                    / "borrow_logs_export.json"
                )

                count = (
                    borrow_manager
                    .export_borrow_logs(
                        output_path
                    )
                )

                print(
                    f"已导出 {count} 条借阅记录："
                    f"{output_path}"
                )

            elif choice == "0":
                return

            else:
                print("无效选项。")
                continue

        except (
            ValueError,
            PyMongoError,
        ) as exc:
            print(f"操作失败：{exc}")

        pause()


def show_category_statistics(
    stat_manager: StatManager,
) -> None:
    records = (
        stat_manager.category_statistics()
    )

    print_records(records)
    pause()


def show_college_top(
    stat_manager: StatManager,
) -> None:
    records = (
        stat_manager.college_borrow_top(5)
    )

    print_records(records)
    pause()


def show_monthly_trend(
    stat_manager: StatManager,
) -> None:
    records = (
        stat_manager.monthly_borrow_trend()
    )

    print_records(records)
    pause()


def show_popular_books(
    stat_manager: StatManager,
) -> None:
    records = (
        stat_manager.popular_books(10)
    )

    print_records(records)
    pause()


def print_gridfs_files(
    records: list[dict[str, Any]],
) -> None:
    if not records:
        print("GridFS 中暂无数字资源。")
        return

    print(f"\nGridFS 文件共 {len(records)} 个：")

    for index, record in enumerate(records, start=1):
        upload_date = record.get("upload_date")
        upload_text = (
            upload_date.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(upload_date, datetime)
            else str(upload_date or "未知")
        )
        print(
            f"[{index}] {record['filename']} | "
            f"{record['length']} 字节 | {upload_text}\n"
            f"    ISBN: {record['isbn']} | "
            f"类型: {record['file_type']} | "
            f"原始文件名: {record['original_filename']}\n"
            f"    GridFS ID: {record['file_id']}"
        )


def gridfs_menu(
    gridfs_manager: GridFSManager,
) -> None:
    while True:
        print(
            """
数字资源管理
1. 批量上传测试资源
2. 查看 GridFS 全部文件
3. 按 ISBN 查询数字资源
4. 按书名查询电子书
5. 下载电子书
6. 下载并执行字节一致性校验
0. 返回主菜单
"""
        )

        choice = input("请选择：").strip()

        try:
            if choice == "1":
                results = (
                    gridfs_manager
                    .batch_upload_test_files()
                )

                print("\n测试数字资源批量上传结果：")

                for index, result in enumerate(
                    results,
                    start=1,
                ):
                    print(
                        f"[{index}] {result['filename']} | "
                        f"ISBN: {result['isbn']} | "
                        f"类型: {result['file_type']} | "
                        f"大小: {result['size']} 字节\n"
                        f"    GridFS ID: {result['file_id']} | "
                        f"状态: {result['status']}"
                    )

                    if result.get("message"):
                        print(
                            f"    原因: {result['message']}"
                        )

            elif choice == "2":
                records = gridfs_manager.list_files()
                print_gridfs_files(records)

            elif choice == "3":
                isbn = input("ISBN：").strip()
                result = gridfs_manager.find_by_isbn(
                    isbn
                )

                if result["status"] == "图书不存在":
                    print(f"图书不存在：ISBN {isbn}")
                else:
                    book = result["book"]
                    print(
                        f"\n图书：{book.get('title', '')} | "
                        f"作者：{book.get('author', '')} | "
                        f"ISBN：{book.get('isbn', '')}"
                    )

                    if not result["resources"]:
                        print("未找到关联资源。")
                    else:
                        print_gridfs_files(
                            result["resources"]
                        )

            elif choice == "4":
                keyword = input("书名关键词：")
                result = (
                    gridfs_manager
                    .search_ebooks_by_title(keyword)
                )
                ebooks = result["ebooks"]

                if result["book_count"] == 0:
                    print("未找到书名匹配的图书。")
                elif not ebooks:
                    print(
                        "已找到匹配图书，但未找到关联电子书。"
                    )
                else:
                    print(
                        f"\n按书名查询到 {len(ebooks)} 个电子书："
                    )

                    for index, ebook in enumerate(
                        ebooks,
                        start=1,
                    ):
                        print(
                            f"[{index}] {ebook['title']} | "
                            f"作者: {ebook['author']} | "
                            f"ISBN: {ebook['isbn']}\n"
                            f"    电子书: "
                            f"{ebook['ebook_filename']} | "
                            f"{ebook['length']} 字节 | "
                            f"GridFS ID: {ebook['file_id']}"
                        )

            elif choice == "5":
                file_id = input(
                    "电子书 GridFS ID："
                ).strip()
                result = gridfs_manager.download_file(
                    file_id,
                    required_type="ebook",
                )
                print(
                    f"{result['status']}。\n"
                    f"本地路径：{result['local_path']}\n"
                    f"GridFS 长度：{result['gridfs_size']} 字节\n"
                    f"本地文件大小："
                    f"{result['downloaded_size']} 字节"
                )

            elif choice == "6":
                file_id = input(
                    "电子书 GridFS ID："
                ).strip()
                result = (
                    gridfs_manager
                    .download_and_verify(file_id)
                )
                print(
                    f"\n原始文件大小："
                    f"{result['original_size']} 字节\n"
                    f"GridFS 文件长度："
                    f"{result['gridfs_size']} 字节\n"
                    f"下载文件大小："
                    f"{result['downloaded_size']} 字节\n"
                    f"本地路径：{result['local_path']}\n"
                    f"校验结论：{result['status']}"
                )

            elif choice == "0":
                return

            else:
                print("无效选项。")
                continue

        except (
            ValueError,
            OSError,
            PyMongoError,
        ) as exc:
            print(f"操作失败：{exc}")

        pause()


def audit_log_menu(
    audit_manager: AuditManager,
) -> None:
    limit_text = input(
        "查看最近多少条日志？"
        "直接回车默认为 20："
    ).strip()

    if limit_text:
        try:
            limit = int(limit_text)

            if limit <= 0:
                raise ValueError

        except ValueError:
            print("数量必须为正整数。")
            pause()
            return

    else:
        limit = 20

    records = (
        audit_manager.recent_operations(
            limit
        )
    )

    print_records(records)
    pause()


def show_main_menu() -> None:
    print(
        """
智慧图书馆数字资源平台

1. 图书检索
2. 图书信息管理
3. 读者信息管理
4. 借阅记录管理
5. 图书分类统计
6. 学院借阅排行
7. 年月借阅趋势
8. 热门图书排行
9. 数字资源管理
10. 操作日志查询

0. 退出系统
"""
    )


def main() -> None:
    client = create_client()

    try:
        if not check_connection(client):
            print(
                "MongoDB 连接失败，请检查数据库服务、"
                "认证账号和 config/.env。"
            )
            return

        db = get_database(client)

        audit_manager = AuditManager(db)

        book_manager = BookManager(
            db,
            audit_manager,
        )

        reader_manager = ReaderManager(
            db,
            audit_manager,
        )

        borrow_manager = BorrowManager(
            db,
            audit_manager,
        )

        stat_manager = StatManager(
            db,
            audit_manager,
        )

        gridfs_manager = GridFSManager(
            db,
            audit_manager,
        )

        while True:
            show_main_menu()

            choice = input(
                "请选择功能："
            ).strip()

            if choice == "1":
                book_search_menu(
                    book_manager
                )

            elif choice == "2":
                book_manage_menu(
                    book_manager
                )

            elif choice == "3":
                reader_manage_menu(
                    reader_manager
                )

            elif choice == "4":
                borrow_manage_menu(
                    borrow_manager
                )

            elif choice == "5":
                show_category_statistics(
                    stat_manager
                )

            elif choice == "6":
                show_college_top(
                    stat_manager
                )

            elif choice == "7":
                show_monthly_trend(
                    stat_manager
                )

            elif choice == "8":
                show_popular_books(
                    stat_manager
                )

            elif choice == "9":
                gridfs_menu(
                    gridfs_manager
                )

            elif choice == "10":
                audit_log_menu(
                    audit_manager
                )

            elif choice == "0":
                print("系统已退出。")
                break

            else:
                print(
                    "无效选项，请重新输入。"
                )

    except KeyboardInterrupt:
        print(
            "\n操作已取消，系统退出。"
        )

    except PyMongoError as exc:
        print(
            f"\n数据库操作失败：{exc}"
        )

    finally:
        client.close()


if __name__ == "__main__":
    main()
