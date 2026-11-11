"""复现索引前后执行计划实验，并恢复任务二规划的全部业务索引。

脚本会先删除 ``INDEX_NAMES`` 中列出的业务索引，再执行对比并重建这些索引；
已完成并确认的实验环境不应仅为重复验证而再次运行本脚本。
"""

import os
from pathlib import Path
from pprint import pformat

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / "config" / ".env"
REPORT_FILE = PROJECT_ROOT / "docs" / "任务3_索引执行计划对比.md"

# 从本地配置文件读取数据库地址，避免在代码中写死虚拟机 IP
load_dotenv(ENV_FILE)

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("MONGODB_DB_NAME", "smart_library")

if not MONGODB_URI:
    raise RuntimeError("未配置 MONGODB_URI")


# 记录任务二规划的业务索引名称，便于实验前统一删除并恢复无索引状态
INDEX_NAMES = {
    "books": [
        "uq_books_isbn",
        "ix_books_category_price",
        "ix_books_tags",
        "ix_books_publish_date",
        "ix_books_rating_desc",
    ],
    "readers": [
        "uq_readers_card_no",
    ],
    "borrow_logs": [
        "ix_borrow_reader_date",
        "ix_borrow_book",
        "ix_borrow_date",
    ],
    "audit_logs": [
        "ix_audit_operate_time_desc",
    ],
}


def drop_test_indexes(db):
    """删除任务二规划的业务索引，保留 MongoDB 默认的 _id_ 索引。"""
    for collection_name, index_names in INDEX_NAMES.items():
        collection = db[collection_name]

        existing = {
            index["name"]
            for index in collection.list_indexes()
        }

        for index_name in index_names:
            if index_name in existing:
                collection.drop_index(index_name)


def collect_stages(obj):
    """
    递归提取 explain 执行计划中的阶段名称，
    用于判断查询采用 COLLSCAN 还是 IXSCAN。
    """
    stages = []

    if isinstance(obj, dict):
        stage = obj.get("stage")

        if stage:
            stages.append(stage)

        for value in obj.values():
            stages.extend(collect_stages(value))

    elif isinstance(obj, list):
        for value in obj:
            stages.extend(collect_stages(value))

    return stages


def explain_find(
    db,
    collection_name,
    query_filter,
    sort=None,
    limit=None,
    projection=None,
):
    """
    执行 find 查询的 executionStats 分析，
    提取实验中需要比较的核心性能指标。
    """
    command = {
        "find": collection_name,
        "filter": query_filter,
    }

    if sort:
        command["sort"] = sort

    if limit:
        command["limit"] = limit

    if projection:
        command["projection"] = projection

    result = db.command(
        "explain",
        command,
        verbosity="executionStats",
    )

    stats = result["executionStats"]
    planner = result["queryPlanner"]["winningPlan"]

    # 执行计划可能存在嵌套结构，因此递归提取并去除重复阶段
    stages = []

    for stage in collect_stages(planner):
        if stage not in stages:
            stages.append(stage)

    return {
        "stages": stages,
        "executionTimeMillis": stats.get(
            "executionTimeMillis",
            0,
        ),
        "nReturned": stats.get(
            "nReturned",
            0,
        ),
        "totalDocsExamined": stats.get(
            "totalDocsExamined",
            0,
        ),
        "totalKeysExamined": stats.get(
            "totalKeysExamined",
            0,
        ),
    }


def create_indexes(db):
    """按照任务二最终确定的索引规划创建全部业务索引。"""

    # ISBN 和借阅证号作为业务唯一标识，建立唯一索引
    db.books.create_index(
        [("isbn", ASCENDING)],
        unique=True,
        name="uq_books_isbn",
    )

    # 支撑“类别 + 价格区间”的组合检索
    db.books.create_index(
        [
            ("category", ASCENDING),
            ("price", ASCENDING),
        ],
        name="ix_books_category_price",
    )

    # tags 为数组字段，MongoDB 会自动建立多键索引
    db.books.create_index(
        [("tags", ASCENDING)],
        name="ix_books_tags",
    )

    db.books.create_index(
        [("publish_date", ASCENDING)],
        name="ix_books_publish_date",
    )

    # 对应按评分降序获取 Top 10 图书的查询
    db.books.create_index(
        [("rating", DESCENDING)],
        name="ix_books_rating_desc",
    )

    db.readers.create_index(
        [("card_no", ASCENDING)],
        unique=True,
        name="uq_readers_card_no",
    )

    # 同时支持按读者筛选和按借阅时间倒序获取历史记录
    db.borrow_logs.create_index(
        [
            ("reader_card", ASCENDING),
            ("borrow_date", DESCENDING),
        ],
        name="ix_borrow_reader_date",
    )

    db.borrow_logs.create_index(
        [("book_isbn", ASCENDING)],
        name="ix_borrow_book",
    )

    db.borrow_logs.create_index(
        [("borrow_date", ASCENDING)],
        name="ix_borrow_date",
    )

    # 支撑最近 100 条操作日志的倒序查询
    db.audit_logs.create_index(
        [("operate_time", DESCENDING)],
        name="ix_audit_operate_time_desc",
    )


def print_comparison(title, before, after):
    """在终端输出同一查询建立索引前后的核心指标。"""
    print(title)

    print(
        "建索引前："
        f"阶段={','.join(before['stages'])}，"
        f"耗时={before['executionTimeMillis']} ms，"
        f"扫描文档={before['totalDocsExamined']}，"
        f"扫描索引键={before['totalKeysExamined']}，"
        f"返回={before['nReturned']}"
    )

    print(
        "建索引后："
        f"阶段={','.join(after['stages'])}，"
        f"耗时={after['executionTimeMillis']} ms，"
        f"扫描文档={after['totalDocsExamined']}，"
        f"扫描索引键={after['totalKeysExamined']}，"
        f"返回={after['nReturned']}"
    )

    print("-" * 80)


def write_comparison(report, title, query, before, after):
    """将查询条件及前后执行计划指标写入实验记录。"""
    report.write(f"## {title}\n\n")

    report.write("**查询条件：**\n\n")
    report.write("```javascript\n")
    report.write(query)
    report.write("\n```\n\n")

    report.write("### 建立索引前\n\n")
    report.write("```text\n")
    report.write(
        pformat(
            before,
            sort_dicts=False,
        )
    )
    report.write("\n```\n\n")

    report.write("### 建立索引后\n\n")
    report.write("```text\n")
    report.write(
        pformat(
            after,
            sort_dicts=False,
        )
    )
    report.write("\n```\n\n")


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

        # 先恢复到无业务索引状态，保证“建索引前”的实验结果真实有效
        drop_test_indexes(db)

        # 第一组实验复用任务三的类别和价格组合检索
        query1_filter = {
            "category": "计算机",
            "price": {
                "$gte": 50,
                "$lte": 100,
            },
        }

        before_query1 = explain_find(
            db,
            "books",
            query1_filter,
            projection={
                "_id": 0,
                "title": 1,
                "category": 1,
                "price": 1,
            },
        )

        # 从现有借阅流水中取得真实读者编号，避免人为构造测试数据
        sample_reader = db.borrow_logs.find_one(
            {},
            {
                "_id": 0,
                "reader_card": 1,
            },
        )

        if not sample_reader:
            raise RuntimeError(
                "borrow_logs 中没有可用于索引实验的数据"
            )

        reader_card = sample_reader["reader_card"]

        # 第二组实验测试读者借阅历史查询和时间倒序排序
        query2_filter = {
            "reader_card": reader_card,
        }

        before_query2 = explain_find(
            db,
            "borrow_logs",
            query2_filter,
            sort={
                "borrow_date": -1,
            },
            limit=20,
            projection={
                "_id": 0,
                "reader_card": 1,
                "book_isbn": 1,
                "borrow_date": 1,
                "status": 1,
            },
        )

        # 完成无索引测试后，再一次性创建任务二规划的全部索引
        create_indexes(db)

        # 使用完全相同的查询重新获取执行计划，保证前后结果可比
        after_query1 = explain_find(
            db,
            "books",
            query1_filter,
            projection={
                "_id": 0,
                "title": 1,
                "category": 1,
                "price": 1,
            },
        )

        after_query2 = explain_find(
            db,
            "borrow_logs",
            query2_filter,
            sort={
                "borrow_date": -1,
            },
            limit=20,
            projection={
                "_id": 0,
                "reader_card": 1,
                "book_isbn": 1,
                "borrow_date": 1,
                "status": 1,
            },
        )

        print("\n任务三：索引执行计划前后对比\n")

        print_comparison(
            "[I1] books：类别 + 价格区间查询",
            before_query1,
            after_query1,
        )

        print_comparison(
            f"[I2] borrow_logs：读者 {reader_card} 的最近借阅记录",
            before_query2,
            after_query2,
        )

        print("\n已创建索引：")

        # 输出各集合最终索引，便于直接作为任务三索引清单留档
        for collection_name in INDEX_NAMES:
            print(f"\n{collection_name}")

            for index in db[
                collection_name
            ].list_indexes():

                print(
                    f"  {index['name']}: "
                    f"{dict(index['key'])}"
                )

        print(
            "\n[通过] 索引清单已创建，"
            "两组查询执行计划前后对比完成。"
        )

        query1_text = """db.books.find({
  category: "计算机",
  price: { $gte: 50, $lte: 100 }
})"""

        query2_text = f"""db.borrow_logs.find({{
  reader_card: "{reader_card}"
}}).sort({{
  borrow_date: -1
}}).limit(20)"""

        # 自动生成实验记录，后续可直接用于报告整理
        with REPORT_FILE.open(
            "w",
            encoding="utf-8",
        ) as report:

            report.write(
                "# 任务三：索引清单与执行计划对比\n\n"
            )

            report.write(
                "本实验分别在目标索引建立前后执行相同查询，"
                "记录执行阶段、耗时、扫描文档数、扫描索引键数"
                "及返回记录数。\n\n"
            )

            write_comparison(
                report,
                "I1 类别与价格复合查询",
                query1_text,
                before_query1,
                after_query1,
            )

            write_comparison(
                report,
                "I2 读者借阅记录查询",
                query2_text,
                before_query2,
                after_query2,
            )

            report.write("## 最终索引清单\n\n")

            for collection_name in INDEX_NAMES:
                report.write(
                    f"### {collection_name}\n\n"
                )

                for index in db[
                    collection_name
                ].list_indexes():

                    report.write(
                        f"- `{index['name']}`："
                        f"`{dict(index['key'])}`\n"
                    )

                report.write("\n")

        print(
            "\n执行记录已保存："
            f"{REPORT_FILE}"
        )

    finally:
        client.close()


if __name__ == "__main__":
    main()
