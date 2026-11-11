"""执行任务三五项统计，并以 upsert 方式保存分类统计结果。"""

import os
from datetime import datetime, timezone
from pathlib import Path
from pprint import pformat

from dotenv import load_dotenv
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / "config" / ".env"
REPORT_FILE = PROJECT_ROOT / "docs" / "任务3_统计执行记录.md"

load_dotenv(ENV_FILE)

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("MONGODB_DB_NAME", "smart_library")

if not MONGODB_URI:
    raise RuntimeError("未配置 MONGODB_URI")


def clean_docs(docs):
    result = []

    for doc in docs:
        item = dict(doc)
        item.pop("_id", None)
        result.append(item)

    return result


def write_result(report, title, description, pipeline_text, result):
    report.write(f"## {title}\n\n")
    report.write(f"**统计要求：** {description}\n\n")

    report.write("**聚合管道：**\n\n")
    report.write("```javascript\n")
    report.write(pipeline_text)
    report.write("\n```\n\n")

    report.write(f"**结果条数：{len(result)}**\n\n")

    report.write("**统计结果：**\n\n")
    report.write("```text\n")
    report.write(
        pformat(
            clean_docs(result),
            width=120,
            sort_dicts=False,
        )
    )
    report.write("\n```\n\n")


def print_summary(no, name, result):
    print(f"[S{no}] {name}")
    print(f"结果条数：{len(result)}")
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
        borrow_logs = db["borrow_logs"]
        stat_result = db["stat_result"]

        # S1：按类别统计藏书量、平均价格和平均评分
        category_pipeline = [
            {
                "$group": {
                    "_id": "$category",
                    "book_count": {"$sum": 1},
                    "avg_price": {"$avg": "$price"},
                    "avg_rating": {"$avg": "$rating"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "category": "$_id",
                    "book_count": 1,
                    "avg_price": {"$round": ["$avg_price", 2]},
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                }
            },
            {
                "$sort": {
                    "category": 1
                }
            },
        ]

        category_result = list(
            books.aggregate(category_pipeline)
        )

        category_pipeline_text = """db.books.aggregate([
  {
    $group: {
      _id: "$category",
      book_count: { $sum: 1 },
      avg_price: { $avg: "$price" },
      avg_rating: { $avg: "$rating" }
    }
  },
  {
    $project: {
      _id: 0,
      category: "$_id",
      book_count: 1,
      avg_price: { $round: ["$avg_price", 2] },
      avg_rating: { $round: ["$avg_rating", 2] }
    }
  },
  { $sort: { category: 1 } }
])"""

        # S2：关联 readers，统计各学院借阅量 Top 5
        college_pipeline = [
            {
                "$lookup": {
                    "from": "readers",
                    "localField": "reader_card",
                    "foreignField": "card_no",
                    "as": "reader",
                }
            },
            {
                "$unwind": "$reader"
            },
            {
                "$group": {
                    "_id": "$reader.college",
                    "borrow_count": {"$sum": 1},
                }
            },
            {
                "$sort": {
                    "borrow_count": -1,
                    "_id": 1,
                }
            },
            {
                "$limit": 5
            },
            {
                "$project": {
                    "_id": 0,
                    "college": "$_id",
                    "borrow_count": 1,
                }
            },
        ]

        college_result = list(
            borrow_logs.aggregate(college_pipeline)
        )

        college_pipeline_text = """db.borrow_logs.aggregate([
  {
    $lookup: {
      from: "readers",
      localField: "reader_card",
      foreignField: "card_no",
      as: "reader"
    }
  },
  { $unwind: "$reader" },
  {
    $group: {
      _id: "$reader.college",
      borrow_count: { $sum: 1 }
    }
  },
  { $sort: { borrow_count: -1, _id: 1 } },
  { $limit: 5 },
  {
    $project: {
      _id: 0,
      college: "$_id",
      borrow_count: 1
    }
  }
])"""

        # S3：按年月统计借阅趋势
        trend_pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m",
                            "date": "$borrow_date",
                            "timezone": "Asia/Shanghai",
                        }
                    },
                    "borrow_count": {"$sum": 1},
                }
            },
            {
                "$sort": {
                    "_id": 1
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "month": "$_id",
                    "borrow_count": 1,
                }
            },
        ]

        trend_result = list(
            borrow_logs.aggregate(trend_pipeline)
        )

        trend_pipeline_text = """db.borrow_logs.aggregate([
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m",
          date: "$borrow_date",
          timezone: "Asia/Shanghai"
        }
      },
      borrow_count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      month: "$_id",
      borrow_count: 1
    }
  }
])"""

        # S4：按 borrow_logs 的真实流水次数统计热门图书 Top 10，
        # 再关联 books 获取书名和馆藏位置
        popular_pipeline = [
            {
                "$group": {
                    "_id": "$book_isbn",
                    "borrow_count": {"$sum": 1},
                }
            },
            {
                "$sort": {
                    "borrow_count": -1,
                    "_id": 1,
                }
            },
            {
                "$limit": 10
            },
            {
                "$lookup": {
                    "from": "books",
                    "localField": "_id",
                    "foreignField": "isbn",
                    "as": "book",
                }
            },
            {
                "$unwind": "$book"
            },
            {
                "$project": {
                    "_id": 0,
                    "isbn": "$_id",
                    "title": "$book.title",
                    "borrow_count": 1,
                    "location": "$book.location",
                }
            },
        ]

        popular_result = list(
            borrow_logs.aggregate(popular_pipeline)
        )

        popular_pipeline_text = """db.borrow_logs.aggregate([
  {
    $group: {
      _id: "$book_isbn",
      borrow_count: { $sum: 1 }
    }
  },
  { $sort: { borrow_count: -1, _id: 1 } },
  { $limit: 10 },
  {
    $lookup: {
      from: "books",
      localField: "_id",
      foreignField: "isbn",
      as: "book"
    }
  },
  { $unwind: "$book" },
  {
    $project: {
      _id: 0,
      isbn: "$_id",
      title: "$book.title",
      borrow_count: 1,
      location: "$book.location"
    }
  }
])"""

        # S5：将分类统计结果写入 stat_result
        # 使用 category 作为稳定业务标识，重复运行时更新而不是重复插入
        generated_at = datetime.now(timezone.utc)

        for item in category_result:
            stat_result.update_one(
                {
                    "category": item["category"]
                },
                {
                    "$set": {
                        "category": item["category"],
                        "book_count": item["book_count"],
                        "avg_price": item["avg_price"],
                        "avg_rating": item["avg_rating"],
                        "generated_at": generated_at,
                    }
                },
                upsert=True,
            )

        stored_results = list(
            stat_result.find(
                {},
                {
                    "_id": 0,
                    "category": 1,
                    "book_count": 1,
                    "avg_price": 1,
                    "avg_rating": 1,
                    "generated_at": 1,
                },
            ).sort("category", 1)
        )

        print("\n任务三：5 项统计功能执行结果\n")

        print_summary(
            1,
            "按类别统计藏书量、平均价格和平均评分",
            category_result,
        )

        print_summary(
            2,
            "各学院借阅总量 Top 5",
            college_result,
        )

        print_summary(
            3,
            "按年月统计借阅趋势",
            trend_result,
        )

        print_summary(
            4,
            "借阅次数最多的图书 Top 10",
            popular_result,
        )
        print("\n[S4] 热门图书 Top 10 详细结果")

        for rank, item in enumerate(popular_result, start=1):
            location = item.get("location") or {}
            print(
                f"{rank:02d}. {item.get('title', '-')}"
                f" | ISBN={item.get('isbn', '-')}"
                f" | 借阅次数={item.get('borrow_count', 0)}"
                f" | 楼层={location.get('floor', '-')}"
                f" | 书架={location.get('shelf', '-')}"
                f" | 复本数={location.get('copies', '-')}"
            )
        print_summary(
            5,
            "分类统计结果写入 stat_result",
            stored_results,
        )

        print(
            f"stat_result 当前文档数："
            f"{stat_result.count_documents({})}"
        )

        print(
            "\n[通过] 5 项统计功能均已执行完成。"
        )

        # 生成统计功能执行记录
        with REPORT_FILE.open(
            "w",
            encoding="utf-8",
        ) as report:

            report.write(
                "# 任务三：统计功能执行记录\n\n"
            )

            report.write(
                f"- 数据库：`{DATABASE_NAME}`\n"
                f"- 图书记录：{books.count_documents({})}\n"
                f"- 借阅流水：{borrow_logs.count_documents({})}\n\n"
            )

            write_result(
                report,
                "S1 图书分类统计",
                "按类别统计藏书量、平均价格和平均评分。",
                category_pipeline_text,
                category_result,
            )

            write_result(
                report,
                "S2 学院借阅量排行",
                "关联 readers 集合，统计各学院借阅总量并取前 5 名。",
                college_pipeline_text,
                college_result,
            )

            write_result(
                report,
                "S3 年月借阅趋势",
                "按借阅发生的年月统计借阅次数。",
                trend_pipeline_text,
                trend_result,
            )

            write_result(
                report,
                "S4 热门图书 Top 10",
                "根据借阅流水统计借阅次数最多的 10 本图书，并关联馆藏位置。",
                popular_pipeline_text,
                popular_result,
            )

            report.write(
                "## S5 分类统计结果落库\n\n"
            )
            report.write(
                "S1 的分类统计结果已采用 upsert 方式写入 "
                "`stat_result` 集合，重复运行不会产生重复分类记录。\n\n"
            )
            report.write(
                f"**stat_result 文档数：{len(stored_results)}**\n\n"
            )

            report.write("```text\n")
            report.write(
                pformat(
                    clean_docs(stored_results),
                    width=120,
                    sort_dicts=False,
                )
            )
            report.write("\n```\n")

        print(
            "\n执行记录已保存："
            f"{REPORT_FILE}"
        )

    finally:
        client.close()


if __name__ == "__main__":
    main()
