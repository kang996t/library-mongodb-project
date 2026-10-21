# 图书情报检索与统计平台

基于 Python 和 MongoDB 的课程实训项目，提供图书查询、读者统计、借阅登记、归还以及聚合统计等命令行功能。

## 项目结构

```text
.
├─ scripts/
│  ├─ mongodb_connect.py
│  ├─ book_manager.py
│  ├─ reader_manager.py
│  ├─ borrow_manager.py
│  ├─ stat_manager.py
│  └─ main.py
├─ data/
│  ├─ books.txt
│  ├─ readers.txt
│  ├─ borrow_logs.txt
│  ├─ library.books.json
│  └─ library.category_stats.json
├─ requirements.txt
├─ .env.example
├─ 图书情报检索与统计平台_项目报告.docx
├─ 图书情报检索与统计平台_技术文档.pdf
└─ README.md
```

## 运行环境

- Python 3.9 或更高版本
- MongoDB 服务：`192.168.121.134:27017`
- 数据库：`library`
- 用户名：`libWriter`
- 认证库：`library`

## 安装依赖

建议在项目目录创建独立虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 配置密码

程序只从环境变量 `MONGO_PASSWORD` 读取密码，不在源码中保存真实密码。PowerShell 当前会话可使用：

```powershell
$env:MONGO_PASSWORD = "你的实际 MongoDB 密码"
```

`.env.example` 仅用于说明所需变量；程序不会自动读取 `.env` 文件。

## 准备数据

程序不会自动初始化数据库或导入数据。如果目标数据库中已经存在数据，请不要重复导入，以免产生重复记录。

对于全新且已完成用户授权的 `library` 数据库，可按需使用 `mongoimport` 导入 `data` 中的 JSON 数组文件。省略命令行密码参数时，`mongoimport` 会交互式询问密码。例如：

```powershell
mongoimport --host 192.168.121.134 --port 27017 --username libWriter --authenticationDatabase library --db library --collection books --file data/books.txt --jsonArray
mongoimport --host 192.168.121.134 --port 27017 --username libWriter --authenticationDatabase library --db library --collection readers --file data/readers.txt --jsonArray
```

`borrow_logs` 是时间序列集合，应先由数据库管理员按 `borrow_date` 时间字段创建，再导入 `data/borrow_logs.txt`。项目运行和验证过程不会自动执行这些导入命令。

## 启动程序

```powershell
python scripts/main.py
```

启动后程序会测试 MongoDB 连接，显示 `books`、`readers`、`borrow_logs` 和 `category_stats` 的文档数量，然后进入中文菜单。查询操作不会修改数据；只有用户明确选择新增、修改、删除、借阅或归还操作时才会写入数据库。

## 安全说明

- `.env`、本地虚拟环境、IDE 配置和 Python 缓存均已加入 `.gitignore`。
- 不要将真实 MongoDB 密码、GitHub Token 或其他密钥提交到仓库。
