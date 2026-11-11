# 智慧图书馆数字资源平台（MongoDB 期末项目）

本目录为《NoSQL 数据库技术与应用》期末综合项目，依据最新项目报告整理。任务三、四为 Python 单机业务应用；任务五、六使用成员 A 最终完成的 CentOS MongoDB 副本集及分片集群配置。**不包含旧的成员 B 交接文档、配置模板或实验脚本。**

## 交付目录

- `src/`：Python 主菜单、统一 MongoDB 连接模块和业务管理模块。
- `scripts/`：数据初始化、导入、查询、统计、权限、索引及任务五客户端探针脚本。
- `config/.env.example`：应用连接配置示例（不包含真实账号密码）。
- `config/standalone/`：真实单机 MongoDB 配置（27018）。
- `config/replica-set/`：真实 `libraryRS` 副本集配置（27117/27118/27119，27120 为临时节点）。
- `config/sharding/`：真实 `configRS`、`shard1RS`、`shard2RS`、mongos 配置（27219/27211/27212/27200）。
- `data/`：原始图书、读者、借阅流水和六个 GridFS 样例文件。
- `docs/`：期末项目报告、配置说明及任务三四实验文档。
- `evidence/task3/`：任务三独立截图；其余任务的截图见项目报告内嵌图及既有附录（如另有独立附录，需补充上传）。
- `outputs/`：业务导出文件、下载校验样例、故障转移探针日志等。

## 运行要求

1. Python 3.13、MongoDB 8.0 系列、PyMongo 4.x。
2. 创建 Python 虚拟环境并安装依赖：

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item config\.env.example config\.env
   ```

3. 根据实际 MongoDB 地址及账号，编辑本机 `config/.env`，不要提交该文件。
4. 使用已初始化的单机业务数据库启动主程序：

   ```powershell
   python src/main.py
   ```

空数据库初始化与数据导入见 `scripts/init_database.py` 和 `scripts/import_data.py`。不要对已有业务数据重复导入。`scripts/task3_indexes.py` 会临时调整业务索引进行执行计划测量，不应在生产数据库上运行。

## 数据、拓扑与限制

- 任务给定数据：books 50 条，readers 30 条，borrow_logs 3000 条。
- 单机基线：27018（`smart_library`）。
- 任务五：`libraryRS` 的三节点进程级故障转移实验；27120 为节点增删临时实例。
- 任务六：独立分片集群，两个单成员分片 `shard1RS` / `shard2RS`；路由 `mongos` 27200。
- 配置文件保留实验虚拟机地址 `192.168.121.134`、本机绝对路径和 keyfile **路径**作为可核验实验记录；跨环境复现需要调整地址、目录、文件权限，并自行生成密钥。仓库不包含真实密钥。
- 此仓库内容在当前检查环境完成了 Python 语法层面的审查，但**未在实际 MongoDB 服务上重新做全部集成运行验收**。

## 提交说明

本项目同时保存于旧课程仓库的 `smart-library-final-project/` 以及独立仓库 `smart-library-project`。旧仓库中 `chapter3-library-project/` 是此前第三章小项目，两个项目互不覆盖。
