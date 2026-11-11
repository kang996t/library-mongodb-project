"""执行任务三六类检索并生成可核验的 Markdown 记录。"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pprint import pformat

from dotenv import load_dotenv
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / "config" / ".env"
REPORT_FILE = PROJECT_ROOT / "docs" / "任务3_检索执行记录.md"

# 读取本地 MongoDB 配置
load_dotenv(ENV_FILE)

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("MONGODB_DB_NAME", "smart_library")

if not MONGODB_URI:
    raise RuntimeError("未配置 MONGODB_URI")


def format_docs(docs):
    """去除 _id，便于查看和写入实验记录。"""
    result = []

    for doc in docs:
        clean = dict(doc)
        clean.pop("_id", None)
        result.append(clean)

    return result


def write_section(report, title, description, query_text, docs):
    """将查询命令、结果条数和结果内容写入记录文件。"""
    report.write(f"## {title}\n\n")
    report.write(f"**业务要求：** {description}\n\n")

    report.write("**查询命令：**\n\n")
    report.write("```javascript\n")
    report.write(query_text)
    report.write("\n```\n\n")

    report.write(f"**结果条数：{len(docs)}**\n\n")

    report.write("**查询结果：**\n\n")
    report.write("```text\n")
    report.write(
        pformat(
            format_docs(docs),
            width=120,
            sort_dicts=False,
        )
    )
    report.write("\n```\n\n")


def print_summary(no, name, docs):
    print(f"[Q{no}] {name}")
    print(f"结果条数：{len(docs)}")
    print("-" * 60)


def main():
    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
    )

    try:
        client.admin.command("ping")

        db = client[DATABASE_NAME]
        books = db["books"]

        # Q1：按类别和价格区间组合筛选
        q1_filter = {
            "category": "计算机",
            "price": {
                "$gte": 50,
                "$lte": 100,
            },
        }

        q1 = list(
            books.find(
                q1_filter,
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "category": 1,
                    "price": 1,
                },
            ).sort("price", 1)
        )

        q1_text = """db.books.find(
  {
    category: "计算机",
    price: { $gte: 50, $lte: 100 }
  },
  {
    _id: 0,
    isbn: 1,
    title: 1,
    category: 1,
    price: 1
  }
).sort({ price: 1 })"""

        # Q2：同时包含多个指定标签
        q2_filter = {
            "tags": {
                "$all": ["编程", "入门"]
            }
        }

        q2 = list(
            books.find(
                q2_filter,
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "tags": 1,
                },
            )
        )

        q2_text = """db.books.find(
  {
    tags: { $all: ["编程", "入门"] }
  },
  {
    _id: 0,
    isbn: 1,
    title: 1,
    tags: 1
  }
)"""

        # Q3：使用正则表达式实现书名模糊检索
        q3_filter = {
            "title": {
                "$regex": "Python",
                "$options": "i",
            }
        }

        q3 = list(
            books.find(
                q3_filter,
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "author": 1,
                },
            )
        )

        q3_text = r"""db.books.find(
  {
    title: { $regex: "Python", $options: "i" }
  },
  {
    _id: 0,
    isbn: 1,
    title: 1,
    author: 1
  }
)"""

        # Q4：查询 2021—2023 年出版的图书
        # 使用左闭右开时间区间，避免年末时间边界问题
        china_tz = timezone(timedelta(hours=8))

        start_date = datetime(
            2021,
            1,
            1,
            0,
            0,
            0,
            tzinfo=china_tz,
        )

        end_date = datetime(
            2024,
            1,
            1,
            0,
            0,
            0,
            tzinfo=china_tz,
        )

        q4_filter = {
            "publish_date": {
                "$gte": start_date,
                "$lt": end_date,
            }
        }

        q4 = list(
            books.find(
                q4_filter,
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "publish_date": 1,
                },
            ).sort("publish_date", 1)
        )

        q4_text = """db.books.find(
  {
    publish_date: {
      $gte: ISODate("2020-12-31T16:00:00Z"),
      $lt: ISODate("2023-12-31T16:00:00Z")
    }
  },
  {
    _id: 0,
    isbn: 1,
    title: 1,
    publish_date: 1
  }
).sort({ publish_date: 1 })"""

        # Q5：查询缺少 tags 字段的图书
        q5_filter = {
            "tags": {
                "$exists": False
            }
        }

        q5 = list(
            books.find(
                q5_filter,
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                },
            )
        )

        q5_text = """db.books.find(
  {
    tags: { $exists: false }
  },
  {
    _id: 0,
    isbn: 1,
    title: 1
  }
)"""

        # Q6：按评分降序取前 10
        # 同分时按书名排序，保证每次运行结果稳定
        q6 = list(
            books.find(
                {},
                {
                    "_id": 0,
                    "title": 1,
                    "author": 1,
                    "rating": 1,
                },
            )
            .sort(
                [
                    ("rating", -1),
                    ("title", 1),
                ]
            )
            .limit(10)
        )

        q6_text = """db.books.find(
  {},
  {
    _id: 0,
    title: 1,
    author: 1,
    rating: 1
  }
).sort({
  rating: -1,
  title: 1
}).limit(10)"""

        print("\n任务三：6 类检索执行结果\n")

        print_summary(
            1,
            "计算机类 + 价格 50—100 元",
            q1,
        )

        print_summary(
            2,
            '同时包含“编程”和“入门”标签',
            q2,
        )

        print_summary(
            3,
            '书名包含“Python”',
            q3,
        )

        print_summary(
            4,
            "出版年份为 2021—2023",
            q4,
        )

        print_summary(
            5,
            "缺少 tags 字段",
            q5,
        )

        print_summary(
            6,
            "评分降序 Top 10",
            q6,
        )

        total_books = books.count_documents({})

        print(f"books 集合总数：{total_books}")
        print("\n[通过] 6 类检索均已执行完成。")

        # 将查询命令和实际结果写入实验记录
        with REPORT_FILE.open(
            "w",
            encoding="utf-8",
        ) as report:

            report.write("# 任务三：检索功能执行记录\n\n")
            report.write(
                f"- 数据库：`{DATABASE_NAME}`\n"
                f"- 数据集合：`books`\n"
                f"- 集合总文档数：{total_books}\n\n"
            )

            write_section(
                report,
                "Q1 类别与价格区间组合筛选",
                "查询计算机类中价格为 50—100 元的图书。",
                q1_text,
                q1,
            )

            write_section(
                report,
                "Q2 标签多选匹配",
                "查询同时具有“编程”和“入门”两个标签的图书。",
                q2_text,
                q2,
            )

            write_section(
                report,
                "Q3 书名模糊检索",
                "采用正则表达式查询书名中包含“Python”的图书。",
                q3_text,
                q3,
            )

            write_section(
                report,
                "Q4 出版年份范围检索",
                "查询出版年份位于 2021—2023 年的图书。",
                q4_text,
                q4,
            )

            write_section(
                report,
                "Q5 缺失字段查询",
                "查询未设置 tags 字段的图书。",
                q5_text,
                q5,
            )

            write_section(
                report,
                "Q6 评分排序与字段投影",
                "按评分降序获取前 10 本图书，仅返回书名、作者和评分。",
                q6_text,
                q6,
            )

        print(
            "\n执行记录已保存："
            f"{REPORT_FILE}"
        )

    finally:
        client.close()


if __name__ == "__main__":
    main()
