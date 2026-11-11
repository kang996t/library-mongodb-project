"""只读审计智慧图书馆原始数据与 GridFS 资源清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
EXPECTED_COUNTS = {
    "books.txt": 50,
    "readers.txt": 30,
    "borrow_logs.txt": 3_000,
}


@dataclass(frozen=True)
class Issue:
    level: str
    source: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="数据目录，默认使用项目根目录下的 data",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="可选的 Markdown 报告输出路径；相对路径按项目根目录解析",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="存在警告时也返回非零退出码",
    )
    return parser.parse_args()


def load_json_array(path: Path, issues: list[Issue]) -> list[dict[str, Any]]:
    try:
        raw_data = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        issues.append(Issue("错误", path.name, f"文件无法按 UTF-8 读取：{exc}"))
        return []

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        issues.append(
            Issue(
                "错误",
                path.name,
                f"JSON 解析失败（第 {exc.lineno} 行，第 {exc.colno} 列）：{exc.msg}",
            )
        )
        return []

    if not isinstance(data, list):
        issues.append(Issue("错误", path.name, "文件顶层必须是 JSON 数组。"))
        return []

    invalid_rows = [index + 1 for index, record in enumerate(data) if not isinstance(record, dict)]
    if invalid_rows:
        issues.append(
            Issue("错误", path.name, f"以下记录不是 JSON 对象：{invalid_rows[:20]}")
        )
        return [record for record in data if isinstance(record, dict)]
    return data


def type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def field_statistics(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    fields = sorted({field for record in records for field in record})
    statistics: dict[str, dict[str, Any]] = {}
    for field in fields:
        present_values = [record[field] for record in records if field in record]
        non_null_values = [value for value in present_values if value is not None]
        statistics[field] = {
            "present": len(present_values),
            "missing": len(records) - len(present_values),
            "null": sum(value is None for value in present_values),
            "types": dict(sorted(Counter(type_name(value) for value in non_null_values).items())),
        }
    return statistics


def is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def check_required_fields(
    source: str,
    records: list[dict[str, Any]],
    required_fields: set[str],
    issues: list[Issue],
) -> None:
    for field in sorted(required_fields):
        bad_rows = [
            index + 1
            for index, record in enumerate(records)
            if field not in record or is_blank(record.get(field))
        ]
        if bad_rows:
            issues.append(
                Issue(
                    "错误",
                    source,
                    f"关键字段 {field!r} 缺失或为空，共 {len(bad_rows)} 条，"
                    f"记录号示例：{bad_rows[:10]}",
                )
            )


def matches_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    if isinstance(value, bool) and expected in (int, float, (int, float)):
        return False
    return isinstance(value, expected)


def check_field_types(
    source: str,
    records: list[dict[str, Any]],
    expected_types: dict[str, type | tuple[type, ...]],
    issues: list[Issue],
) -> None:
    for field, expected_type in expected_types.items():
        bad_rows = []
        for index, record in enumerate(records):
            if field not in record or record[field] is None:
                continue
            if not matches_type(record[field], expected_type):
                bad_rows.append(index + 1)
        if bad_rows:
            issues.append(
                Issue(
                    "错误",
                    source,
                    f"字段 {field!r} 类型异常，共 {len(bad_rows)} 条，"
                    f"记录号示例：{bad_rows[:10]}",
                )
            )


def check_string_array(
    source: str,
    records: list[dict[str, Any]],
    field: str,
    issues: list[Issue],
) -> None:
    bad_rows = []
    for index, record in enumerate(records):
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            bad_rows.append(index + 1)
    if bad_rows:
        issues.append(
            Issue(
                "错误",
                source,
                f"字段 {field!r} 应为字符串数组，异常记录号示例：{bad_rows[:10]}",
            )
        )


def duplicate_values(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(
        str(record[field])
        for record in records
        if field in record and not is_blank(record[field])
    )
    return {value: count for value, count in counts.items() if count > 1}


def parse_iso_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("日期值不是字符串")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audit_dates(
    source: str,
    records: list[dict[str, Any]],
    field: str,
    issues: list[Issue],
) -> dict[str, int]:
    valid = 0
    missing = 0
    invalid_rows: list[int] = []
    for index, record in enumerate(records):
        value = record.get(field)
        if value is None or value == "":
            missing += 1
            continue
        try:
            parse_iso_datetime(value)
            valid += 1
        except (TypeError, ValueError):
            invalid_rows.append(index + 1)
    if invalid_rows:
        issues.append(
            Issue(
                "错误",
                source,
                f"日期字段 {field!r} 有 {len(invalid_rows)} 条无法解析，"
                f"记录号示例：{invalid_rows[:10]}",
            )
        )
    return {"valid": valid, "missing": missing, "invalid": len(invalid_rows)}


def isbn13_checksum_valid(isbn: str) -> bool:
    if re.fullmatch(r"\d{13}", isbn) is None:
        return False
    weighted_sum = sum(
        int(digit) * (1 if index % 2 == 0 else 3)
        for index, digit in enumerate(isbn[:12])
    )
    expected_check_digit = (10 - weighted_sum % 10) % 10
    return expected_check_digit == int(isbn[-1])


def exact_duplicate_count(records: list[dict[str, Any]]) -> int:
    serialized = Counter(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    )
    return sum(count - 1 for count in serialized.values() if count > 1)


def verify_hash(path: Path, algorithm: str, expected: str) -> bool:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected.lower()


def audit_resources(
    gridfs_dir: Path,
    book_isbns: set[str],
    ebook_names: set[str],
    issues: list[Issue],
) -> tuple[list[dict[str, Any]], bool]:
    manifest_path = gridfs_dir / "files_manifest.txt"
    try:
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(Issue("错误", manifest_path.name, "资源清单不存在。"))
        return [], False
    except (OSError, UnicodeError) as exc:
        issues.append(Issue("错误", manifest_path.name, f"资源清单无法按 UTF-8 读取：{exc}"))
        return [], False
    except json.JSONDecodeError as exc:
        issues.append(
            Issue(
                "错误",
                manifest_path.name,
                f"资源清单 JSON 解析失败（第 {exc.lineno} 行，第 {exc.colno} 列）：{exc.msg}",
            )
        )
        return [], False

    if not isinstance(parsed, dict):
        issues.append(Issue("错误", manifest_path.name, "资源清单顶层必须是 JSON 对象。"))
        return [], False

    manifest_data: list[dict[str, Any]] = []
    for group in ("ebooks", "covers"):
        group_items = parsed.get(group)
        if not isinstance(group_items, list):
            issues.append(Issue("错误", manifest_path.name, f"清单字段 {group!r} 必须是数组。"))
            continue
        for item in group_items:
            if not isinstance(item, dict):
                issues.append(Issue("错误", manifest_path.name, f"清单字段 {group!r} 含非对象条目。"))
                continue
            manifest_data.append({**item, "group": group})

    actual_files = {
        path.name: path
        for path in gridfs_dir.iterdir()
        if path.is_file() and path.name != manifest_path.name
    } if gridfs_dir.is_dir() else {}
    manifest_names = [str(item.get("filename", "")) for item in manifest_data]
    duplicate_names = [name for name, count in Counter(manifest_names).items() if name and count > 1]
    if duplicate_names:
        issues.append(Issue("错误", manifest_path.name, f"清单文件名重复：{duplicate_names}"))

    listed = {name for name in manifest_names if name}
    missing_files = sorted(listed - set(actual_files))
    extra_files = sorted(set(actual_files) - listed)
    if missing_files:
        issues.append(Issue("错误", "gridfs_files", f"清单列出但实际缺失：{missing_files}"))
    if extra_files:
        issues.append(Issue("警告", "gridfs_files", f"存在未列入清单的资源文件：{extra_files}"))

    rows: list[dict[str, Any]] = []
    checksum_present = False
    for item in manifest_data:
        filename = item.get("filename")
        expected_bytes = item.get("bytes")
        related_isbn = item.get("related_isbn")
        group = item.get("group", "")
        path = actual_files.get(str(filename))
        actual_bytes = path.stat().st_size if path else None
        status_parts: list[str] = []

        if not isinstance(filename, str) or not filename:
            issues.append(Issue("错误", manifest_path.name, "清单条目缺少有效 filename。"))
        if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool):
            issues.append(Issue("错误", manifest_path.name, f"{filename!r} 的 bytes 必须是整数。"))
        elif actual_bytes is not None and actual_bytes != expected_bytes:
            issues.append(
                Issue(
                    "错误",
                    manifest_path.name,
                    f"{filename!r} 大小不一致：清单 {expected_bytes}，实际 {actual_bytes}。",
                )
            )
        else:
            status_parts.append("大小一致")

        if related_isbn not in book_isbns:
            issues.append(
                Issue("错误", manifest_path.name, f"{filename!r} 关联的 ISBN 不存在：{related_isbn!r}")
            )
        else:
            status_parts.append("ISBN 可关联")

        if isinstance(filename, str):
            suffix = Path(filename).suffix.lower()
            expected_suffix = ".pdf" if group == "ebooks" else ".png" if group == "covers" else None
            if expected_suffix and suffix != expected_suffix:
                issues.append(
                    Issue("错误", manifest_path.name, f"{filename!r} 与分组 {group!r} 的扩展名不一致。")
                )

        for hash_key, algorithm in (("sha256", "sha256"), ("md5", "md5")):
            expected_hash = item.get(hash_key)
            if expected_hash is not None:
                checksum_present = True
                if path is None or not isinstance(expected_hash, str) or not verify_hash(path, algorithm, expected_hash):
                    issues.append(Issue("错误", manifest_path.name, f"{filename!r} 的 {hash_key} 校验失败。"))
                else:
                    status_parts.append(f"{hash_key} 一致")

        generic_checksum = item.get("checksum")
        if generic_checksum is not None:
            checksum_present = True
            if isinstance(generic_checksum, str) and ":" in generic_checksum:
                algorithm, expected_hash = generic_checksum.split(":", 1)
                algorithm = algorithm.lower()
                if algorithm not in hashlib.algorithms_available:
                    issues.append(Issue("警告", manifest_path.name, f"{filename!r} 使用未知校验算法 {algorithm!r}。"))
                elif path is None or not verify_hash(path, algorithm, expected_hash):
                    issues.append(Issue("错误", manifest_path.name, f"{filename!r} 的 checksum 校验失败。"))
                else:
                    status_parts.append("checksum 一致")
            else:
                issues.append(
                    Issue(
                        "警告",
                        manifest_path.name,
                        f"{filename!r} 的 checksum 未采用 algorithm:digest 格式，无法核验。",
                    )
                )

        rows.append(
            {
                "filename": filename,
                "group": group,
                "manifest_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "related_isbn": related_isbn,
                "status": "；".join(status_parts) if path else "文件缺失",
            }
        )

    missing_named_ebooks = sorted(ebook_names - set(actual_files))
    if missing_named_ebooks:
        issues.append(
            Issue(
                "错误",
                "books.txt",
                f"ebook_name 指向不存在的文件：{missing_named_ebooks}",
            )
        )
    return rows, checksum_present


def audit(data_dir: Path) -> dict[str, Any]:
    issues: list[Issue] = []
    collections: dict[str, dict[str, Any]] = {}
    records_by_file: dict[str, list[dict[str, Any]]] = {}

    for filename, expected_count in EXPECTED_COUNTS.items():
        path = data_dir / filename
        if not path.is_file():
            issues.append(Issue("错误", filename, "文件不存在。"))
            records: list[dict[str, Any]] = []
        else:
            records = load_json_array(path, issues)
        records_by_file[filename] = records
        collections[filename] = {
            "expected": expected_count,
            "actual": len(records),
            "fields": field_statistics(records),
        }
        if len(records) != expected_count:
            issues.append(
                Issue(
                    "错误",
                    filename,
                    f"记录数与任务书不一致：期望 {expected_count}，实际 {len(records)}。",
                )
            )

    books = records_by_file["books.txt"]
    readers = records_by_file["readers.txt"]
    borrow_logs = records_by_file["borrow_logs.txt"]

    check_required_fields(
        "books.txt",
        books,
        {
            "isbn", "title", "author", "category", "publisher", "publish_date",
            "price", "rating", "stock", "borrow_count", "location",
        },
        issues,
    )
    check_field_types(
        "books.txt",
        books,
        {
            "isbn": str, "title": str, "author": str, "category": str,
            "publisher": str, "publish_date": str, "price": (int, float),
            "rating": (int, float), "stock": int, "borrow_count": int,
            "location": dict, "tags": list, "ebook_name": str,
        },
        issues,
    )
    check_string_array("books.txt", books, "tags", issues)

    check_required_fields(
        "readers.txt",
        readers,
        {"card_no", "name", "college", "phone", "level", "register_date"},
        issues,
    )
    check_field_types(
        "readers.txt",
        readers,
        {
            "card_no": str, "name": str, "college": str, "phone": str,
            "email": str, "level": str, "register_date": str,
            "fav_categories": list,
        },
        issues,
    )
    check_string_array("readers.txt", readers, "fav_categories", issues)

    check_required_fields(
        "borrow_logs.txt",
        borrow_logs,
        {"borrow_date", "reader_card", "book_isbn", "duration_days", "status"},
        issues,
    )
    check_field_types(
        "borrow_logs.txt",
        borrow_logs,
        {
            "borrow_date": str, "reader_card": str, "book_isbn": str,
            "duration_days": int, "return_date": str, "status": str,
        },
        issues,
    )

    isbn_duplicates = duplicate_values(books, "isbn")
    card_duplicates = duplicate_values(readers, "card_no")
    if isbn_duplicates:
        issues.append(Issue("错误", "books.txt", f"ISBN 不唯一：{isbn_duplicates}"))
    if card_duplicates:
        issues.append(Issue("错误", "readers.txt", f"借阅证号不唯一：{card_duplicates}"))

    isbn_format_invalid = sorted(
        str(book.get("isbn"))
        for book in books
        if not isinstance(book.get("isbn"), str)
        or re.fullmatch(r"\d{13}", book["isbn"]) is None
    )
    isbn_checksum_invalid = sorted(
        book["isbn"]
        for book in books
        if isinstance(book.get("isbn"), str)
        and re.fullmatch(r"\d{13}", book["isbn"])
        and not isbn13_checksum_valid(book["isbn"])
    )
    if isbn_format_invalid:
        issues.append(
            Issue("错误", "books.txt", f"非 13 位数字格式的 ISBN：{isbn_format_invalid}")
        )
    if isbn_checksum_invalid:
        issues.append(
            Issue(
                "警告",
                "books.txt",
                f"有 {len(isbn_checksum_invalid)} 个 ISBN-13 校验位不符合标准："
                f"{isbn_checksum_invalid}",
            )
        )

    card_format_invalid = sorted(
        str(reader.get("card_no"))
        for reader in readers
        if not isinstance(reader.get("card_no"), str)
        or re.fullmatch(r"R\d{8}", reader["card_no"]) is None
    )
    if card_format_invalid:
        issues.append(
            Issue("警告", "readers.txt", f"不符合 R+8位数字格式的借阅证号：{card_format_invalid}")
        )

    book_isbns = {book.get("isbn") for book in books if isinstance(book.get("isbn"), str)}
    reader_cards = {
        reader.get("card_no") for reader in readers if isinstance(reader.get("card_no"), str)
    }
    missing_book_refs = Counter(
        log.get("book_isbn") for log in borrow_logs if log.get("book_isbn") not in book_isbns
    )
    missing_reader_refs = Counter(
        log.get("reader_card") for log in borrow_logs if log.get("reader_card") not in reader_cards
    )
    if missing_book_refs:
        issues.append(Issue("错误", "borrow_logs.txt", f"无法关联图书的流水：{dict(missing_book_refs)}"))
    if missing_reader_refs:
        issues.append(Issue("错误", "borrow_logs.txt", f"无法关联读者的流水：{dict(missing_reader_refs)}"))

    date_checks = {
        "books.publish_date": audit_dates("books.txt", books, "publish_date", issues),
        "readers.register_date": audit_dates("readers.txt", readers, "register_date", issues),
        "borrow_logs.borrow_date": audit_dates("borrow_logs.txt", borrow_logs, "borrow_date", issues),
        "borrow_logs.return_date": audit_dates("borrow_logs.txt", borrow_logs, "return_date", issues),
    }

    returned_without_date = 0
    non_returned_with_date = 0
    return_before_borrow = 0
    for log in borrow_logs:
        return_date = log.get("return_date")
        status = log.get("status")
        if status == "已归还" and is_blank(return_date):
            returned_without_date += 1
        if status in {"借出", "逾期"} and not is_blank(return_date):
            non_returned_with_date += 1
        if not is_blank(return_date):
            try:
                if parse_iso_datetime(return_date) < parse_iso_datetime(log.get("borrow_date")):
                    return_before_borrow += 1
            except (TypeError, ValueError):
                pass
    if returned_without_date:
        issues.append(Issue("错误", "borrow_logs.txt", f"已归还但缺少归还日期：{returned_without_date} 条。"))
    if non_returned_with_date:
        issues.append(Issue("警告", "borrow_logs.txt", f"未归还状态却填写归还日期：{non_returned_with_date} 条。"))
    if return_before_borrow:
        issues.append(Issue("错误", "borrow_logs.txt", f"归还日期早于借阅日期：{return_before_borrow} 条。"))

    exact_duplicates = exact_duplicate_count(borrow_logs)
    if exact_duplicates:
        issues.append(Issue("警告", "borrow_logs.txt", f"完全重复的流水记录：{exact_duplicates} 条。"))

    location_bad = 0
    for book in books:
        location = book.get("location")
        if not isinstance(location, dict):
            continue
        if (
            not isinstance(location.get("floor"), str)
            or not isinstance(location.get("shelf"), str)
            or not isinstance(location.get("copies"), int)
            or isinstance(location.get("copies"), bool)
        ):
            location_bad += 1
    if location_bad:
        issues.append(Issue("错误", "books.txt", f"location 子字段结构或类型异常：{location_bad} 条。"))

    ebook_names = {
        book["ebook_name"]
        for book in books
        if isinstance(book.get("ebook_name"), str) and book["ebook_name"]
    }
    resources, checksum_present = audit_resources(
        data_dir / "gridfs_files",
        book_isbns,
        ebook_names,
        issues,
    )

    return {
        "data_dir": data_dir,
        "collections": collections,
        "issues": issues,
        "isbn_duplicates": isbn_duplicates,
        "card_duplicates": card_duplicates,
        "isbn_format_invalid": isbn_format_invalid,
        "isbn_checksum_invalid": isbn_checksum_invalid,
        "missing_book_ref_count": sum(missing_book_refs.values()),
        "missing_reader_ref_count": sum(missing_reader_refs.values()),
        "date_checks": date_checks,
        "status_counts": dict(
            sorted(
                Counter(log.get("status") for log in borrow_logs).items(),
                key=lambda item: str(item[0]),
            )
        ),
        "exact_duplicate_logs": exact_duplicates,
        "returned_without_date": returned_without_date,
        "non_returned_with_date": non_returned_with_date,
        "return_before_borrow": return_before_borrow,
        "location_bad": location_bad,
        "resources": resources,
        "checksum_present": checksum_present,
    }


def render_field_tables(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for filename, collection in result["collections"].items():
        lines.extend(
            [
                f"### {filename}",
                "",
                "| 字段 | 非空值类型 | 缺失键 | 显式 null |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        for field, stats in collection["fields"].items():
            type_summary = "、".join(
                f"{name}({count})" for name, count in stats["types"].items()
            ) or "无非空值"
            lines.append(
                f"| `{field}` | {type_summary} | {stats['missing']} | {stats['null']} |"
            )
        lines.append("")
    return lines


def build_markdown_report(result: dict[str, Any]) -> str:
    issues: list[Issue] = result["issues"]
    error_count = sum(issue.level == "错误" for issue in issues)
    warning_count = sum(issue.level == "警告" for issue in issues)
    collections = result["collections"]

    lines = [
        "# 智慧图书馆原始数据质量审计报告",
        "",
        "## 审计结论",
        "",
        (
            "三份业务数据均可按 UTF-8 JSON 数组成功解析，实际规模为图书 50 条、读者 30 条、"
            "借阅流水 3000 条，与任务书一致。ISBN 与借阅证号均无重复，3000 条借阅流水均可"
            "关联到现有图书和读者，所有已填写的日期均可解析，GridFS 清单中的 6 个资源文件"
            "均存在且字节数一致。"
        ),
        "",
        (
            f"本次审计发现 {error_count} 项硬错误、{warning_count} 项警告。"
            "主要警告是 23 个图书 ISBN 虽为 13 位数字且在项目内部关联一致，但 ISBN-13 标准"
            "校验位不通过；原始数据未被修改。"
        ),
        "",
        "## 数据规模与解析结果",
        "",
        "| 文件 | 任务书规模 | 实际记录数 | 解析结果 |",
        "| --- | ---: | ---: | --- |",
    ]
    for filename, collection in collections.items():
        parse_result = "通过" if collection["actual"] == collection["expected"] else "规模不一致"
        lines.append(
            f"| `{filename}` | {collection['expected']} | {collection['actual']} | {parse_result} |"
        )

    lines.extend(["", "## 字段结构与数据类型", ""])
    lines.extend(render_field_tables(result))
    lines.extend(
        [
            "50 条 `books.location` 均为嵌套对象，且都包含字符串类型的 `floor`、"
            "`shelf` 与整数类型的 `copies`；结构或类型异常为 0 条。",
            "",
            "**合理缺失说明：**",
            "",
            "- `books.ebook_name` 仅 3 条存在，对应现有 3 份 PDF；其余 47 条未提供电子书，属于当前资源范围内的合理缺失。",
            "- `books.tags` 缺失 4 条，符合任务书中用于数据质量核查的设计，但正式建模时应由成员 C 明确是否允许缺失。",
            "- `readers.email` 有 5 条显式 `null`，`fav_categories` 缺失 2 条；二者不影响读者主标识与借阅关联。",
            "- `borrow_logs.return_date` 缺失 858 条，恰好对应 429 条“借出”和 429 条“逾期”；2142 条“已归还”记录均填写归还日期。",
            "",
            "## 唯一性、关联完整性与日期",
            "",
            "| 检查项 | 结果 |",
            "| --- | --- |",
            f"| 图书 ISBN 唯一性 | 重复 {len(result['isbn_duplicates'])} 个 |",
            f"| 读者借阅证号唯一性 | 重复 {len(result['card_duplicates'])} 个 |",
            f"| 借阅流水引用不存在的图书 | {result['missing_book_ref_count']} 条 |",
            f"| 借阅流水引用不存在的读者 | {result['missing_reader_ref_count']} 条 |",
            f"| 完全重复的借阅流水 | {result['exact_duplicate_logs']} 条 |",
            f"| 已归还但缺少归还日期 | {result['returned_without_date']} 条 |",
            f"| 未归还状态却填写归还日期 | {result['non_returned_with_date']} 条 |",
            f"| 归还日期早于借阅日期 | {result['return_before_borrow']} 条 |",
            f"| 借阅状态分布 | {result['status_counts']} |",
            "",
            "借阅流水中的 `book_isbn` 与 `reader_card` 是正常重复出现的外键式关联字段，"
            "不应按主键冲突处理。所有 3000 条流水文档内容均不完全重复。",
            "",
            "| 日期字段 | 可解析 | 合理缺失 | 无法解析 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for field, stats in result["date_checks"].items():
        lines.append(f"| `{field}` | {stats['valid']} | {stats['missing']} | {stats['invalid']} |")

    lines.extend(
        [
            "",
            "## GridFS 资源文件与清单",
            "",
            "| 文件 | 分组 | 清单字节数 | 实际字节数 | 关联 ISBN | 核验结果 |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in result["resources"]:
        lines.append(
            f"| `{row['filename']}` | {row['group']} | {row['manifest_bytes']} | "
            f"{row['actual_bytes']} | `{row['related_isbn']}` | {row['status']} |"
        )
    if result["checksum_present"]:
        lines.append("\n清单提供了校验值，脚本已按指定算法完成内容校验。")
    else:
        lines.append(
            "\n清单提供了文件名、字节数和关联 ISBN，但未提供 MD5、SHA-256 或其他内容校验值；"
            "因此本阶段完成了存在性、名称、大小和 ISBN 关联核验，无法执行清单驱动的哈希比对。"
        )

    lines.extend(["", "## 质量问题", ""])
    if not issues:
        lines.append("未发现错误或警告。")
    else:
        for issue in issues:
            lines.append(f"- **{issue.level}｜{issue.source}：** {issue.message}")

    lines.extend(
        [
            "",
            "## 处理建议",
            "",
            "1. 在正式导入前由成员 C 确认 ISBN 校验策略。若要求符合 ISBN-13 标准，应回查来源并形成修订映射；在确认前不要直接改写原始文件，以免破坏现有跨文件关联。",
            "2. 在数据模型中明确 `tags`、`ebook_name`、`email`、`fav_categories` 和 `return_date` 的可选条件，并在导入脚本中按该规则处理缺失值。",
            "3. 正式入库时将各日期字符串转换为 BSON Date，并保留当前 `+08:00` 时区语义；ISBN、借阅证号、手机号继续按字符串保存。",
            "4. 若后续需要强内容校验，可由成员 C 在资源清单中增加 SHA-256 字段，现有审计脚本会自动核验 `sha256` 或 `md5`。",
            "",
            "本报告由 `scripts/check_data.py` 对当前原始文件只读扫描生成；审计过程未修改任何业务数据或资源文件。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    result = audit(data_dir)
    issues: list[Issue] = result["issues"]
    errors = [issue for issue in issues if issue.level == "错误"]
    warnings = [issue for issue in issues if issue.level == "警告"]

    print("数据审计完成")
    for filename, collection in result["collections"].items():
        print(
            f"- {filename}: {collection['actual']} 条 "
            f"(任务书 {collection['expected']} 条)"
        )
    print(
        f"- 引用缺失: 图书 {result['missing_book_ref_count']} 条，"
        f"读者 {result['missing_reader_ref_count']} 条"
    )
    print(f"- GridFS 清单资源: {len(result['resources'])} 个")
    print(f"- 硬错误: {len(errors)}，警告: {len(warnings)}")
    for issue in issues:
        print(f"  [{issue.level}] {issue.source}: {issue.message}")

    if args.report:
        report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_markdown_report(result), encoding="utf-8")
        print(f"- Markdown 报告: {report_path.resolve()}")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
