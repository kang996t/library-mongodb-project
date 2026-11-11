from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from gridfs import GridFS, NoFile
from pymongo.database import Database

from audit_manager import AuditManager


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_DIR = PROJECT_ROOT / "data" / "gridfs_files"
DOWNLOAD_DIR = PROJECT_ROOT / "outputs" / "gridfs_downloads"
ALLOWED_FILE_TYPES = {"ebook", "cover"}


class GridFSManager:
    def __init__(
        self,
        db: Database,
        audit_manager: AuditManager,
    ) -> None:
        self.db = db
        self.books = db["books"]
        self.files = db["fs.files"]
        self.fs = GridFS(db)
        self.audit = audit_manager

    @staticmethod
    def _file_record(
        document: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = document.get("metadata") or {}

        return {
            "file_id": str(document.get("_id", "")),
            "filename": document.get("filename", ""),
            "length": int(document.get("length", 0)),
            "upload_date": document.get("uploadDate"),
            "isbn": metadata.get("isbn", ""),
            "file_type": metadata.get("file_type", ""),
            "original_filename": metadata.get(
                "original_filename",
                document.get("filename", ""),
            ),
        }

    @staticmethod
    def _parse_file_id(
        file_id: str | ObjectId,
    ) -> ObjectId:
        if isinstance(file_id, ObjectId):
            return file_id

        value = str(file_id).strip()

        try:
            return ObjectId(value)
        except (InvalidId, TypeError) as exc:
            raise ValueError(
                "GridFS 文件 ID 格式无效"
            ) from exc

    def upload_file(
        self,
        file_path: str | Path,
        isbn: str,
        file_type: str,
    ) -> dict[str, Any]:
        source = Path(file_path)

        if not source.is_file():
            raise ValueError(
                f"文件不存在或不是普通文件：{source}"
            )

        if file_type not in ALLOWED_FILE_TYPES:
            raise ValueError(
                "file_type 只能为 ebook 或 cover"
            )

        isbn = isbn.strip()

        if not isbn:
            raise ValueError("ISBN 不能为空")

        book = self.books.find_one(
            {"isbn": isbn},
            {"_id": 1},
        )

        if book is None:
            raise ValueError(
                f"ISBN {isbn} 对应的图书不存在"
            )

        duplicate_query = {
            "metadata.isbn": isbn,
            "metadata.file_type": file_type,
            "metadata.original_filename": source.name,
        }
        existing = self.files.find_one(
            duplicate_query,
            {
                "_id": 1,
                "length": 1,
            },
        )
        source_size = source.stat().st_size

        if existing is not None:
            return {
                "filename": source.name,
                "isbn": isbn,
                "file_type": file_type,
                "size": source_size,
                "gridfs_size": int(
                    existing.get("length", 0)
                ),
                "file_id": str(existing["_id"]),
                "status": "已存在",
            }

        metadata = {
            "isbn": isbn,
            "file_type": file_type,
            "original_filename": source.name,
        }

        with source.open("rb") as stream:
            file_id = self.fs.put(
                stream,
                filename=source.name,
                metadata=metadata,
            )

        self.audit.log_operation(
            operate_type="上传数字资源",
            target_collection="fs.files",
            target_id=str(file_id),
            operate_detail=(
                f"ISBN={isbn}, 类型={file_type}, "
                f"文件={source.name}, 字节数={source_size}"
            ),
        )

        return {
            "filename": source.name,
            "isbn": isbn,
            "file_type": file_type,
            "size": source_size,
            "gridfs_size": source_size,
            "file_id": str(file_id),
            "status": "上传成功",
        }

    def batch_upload_test_files(
        self,
    ) -> list[dict[str, Any]]:
        manifest_path = RESOURCE_DIR / "files_manifest.txt"

        if not manifest_path.is_file():
            raise ValueError(
                f"测试资源清单不存在：{manifest_path}"
            )

        try:
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"无法读取测试资源清单：{exc}"
            ) from exc

        results: list[dict[str, Any]] = []

        for group_name, file_type in (
            ("ebooks", "ebook"),
            ("covers", "cover"),
        ):
            entries = manifest.get(group_name)

            if not isinstance(entries, list):
                raise ValueError(
                    f"测试资源清单缺少有效的 {group_name} 列表"
                )

            for entry in entries:
                filename = str(
                    entry.get("filename", "")
                ).strip()
                isbn = str(
                    entry.get("related_isbn", "")
                ).strip()

                if (
                    not filename
                    or Path(filename).name != filename
                    or not isbn
                ):
                    results.append(
                        {
                            "filename": filename or "未知文件",
                            "isbn": isbn or "未知 ISBN",
                            "file_type": file_type,
                            "size": 0,
                            "file_id": "-",
                            "status": "上传失败",
                            "message": "资源清单中的文件名或 ISBN 无效",
                        }
                    )
                    continue

                source = RESOURCE_DIR / filename
                actual_size = (
                    source.stat().st_size
                    if source.is_file()
                    else 0
                )

                try:
                    expected_size = int(entry.get("bytes", -1))

                    if actual_size != expected_size:
                        raise ValueError(
                            "文件实际大小与资源清单不一致："
                            f"实际 {actual_size} 字节，"
                            f"清单 {expected_size} 字节"
                        )

                    result = self.upload_file(
                        source,
                        isbn,
                        file_type,
                    )
                except Exception as exc:
                    result = {
                        "filename": filename,
                        "isbn": isbn,
                        "file_type": file_type,
                        "size": actual_size,
                        "file_id": "-",
                        "status": "上传失败",
                        "message": str(exc),
                    }

                results.append(result)

        return results

    def list_files(
        self,
    ) -> list[dict[str, Any]]:
        documents = self.files.find(
            {},
            {
                "filename": 1,
                "length": 1,
                "uploadDate": 1,
                "metadata": 1,
            },
        ).sort("uploadDate", 1)

        return [
            self._file_record(document)
            for document in documents
        ]

    def find_by_isbn(
        self,
        isbn: str,
    ) -> dict[str, Any]:
        isbn = isbn.strip()

        if not isbn:
            raise ValueError("ISBN 不能为空")

        book = self.books.find_one(
            {"isbn": isbn},
            {
                "_id": 0,
                "isbn": 1,
                "title": 1,
                "author": 1,
            },
        )

        if book is None:
            return {
                "status": "图书不存在",
                "book": None,
                "resources": [],
            }

        documents = self.files.find(
            {"metadata.isbn": isbn},
            {
                "filename": 1,
                "length": 1,
                "uploadDate": 1,
                "metadata": 1,
            },
        ).sort(
            [
                ("metadata.file_type", 1),
                ("uploadDate", 1),
            ]
        )
        resources = [
            self._file_record(document)
            for document in documents
        ]

        return {
            "status": (
                "查询成功"
                if resources
                else "未找到关联资源"
            ),
            "book": book,
            "resources": resources,
        }

    def search_ebooks_by_title(
        self,
        keyword: str,
    ) -> dict[str, Any]:
        keyword = keyword.strip()

        if not keyword:
            raise ValueError("书名关键词不能为空")

        books = list(
            self.books.find(
                {
                    "title": {
                        "$regex": re.escape(keyword),
                        "$options": "i",
                    }
                },
                {
                    "_id": 0,
                    "isbn": 1,
                    "title": 1,
                    "author": 1,
                },
            ).sort("title", 1)
        )

        if not books:
            return {
                "book_count": 0,
                "ebooks": [],
            }

        book_by_isbn = {
            str(book.get("isbn", "")): book
            for book in books
        }
        documents = self.files.find(
            {
                "metadata.isbn": {
                    "$in": list(book_by_isbn)
                },
                "metadata.file_type": "ebook",
            },
            {
                "filename": 1,
                "length": 1,
                "metadata": 1,
            },
        ).sort("uploadDate", 1)

        ebooks: list[dict[str, Any]] = []

        for document in documents:
            metadata = document.get("metadata") or {}
            isbn = str(metadata.get("isbn", ""))
            book = book_by_isbn.get(isbn)

            if book is None:
                continue

            ebooks.append(
                {
                    "title": book.get("title", ""),
                    "author": book.get("author", ""),
                    "isbn": isbn,
                    "ebook_filename": metadata.get(
                        "original_filename",
                        document.get("filename", ""),
                    ),
                    "file_id": str(document["_id"]),
                    "length": int(document.get("length", 0)),
                }
            )

        return {
            "book_count": len(books),
            "ebooks": ebooks,
        }

    def download_file(
        self,
        file_id: str | ObjectId,
        required_type: str | None = None,
    ) -> dict[str, Any]:
        object_id = self._parse_file_id(file_id)

        try:
            grid_out = self.fs.get(object_id)
        except NoFile as exc:
            raise ValueError(
                f"未找到 GridFS 文件：{object_id}"
            ) from exc

        metadata = grid_out.metadata or {}
        file_type = metadata.get("file_type", "")

        if required_type and file_type != required_type:
            raise ValueError(
                f"该文件类型为 {file_type or '未知'}，"
                f"不是 {required_type}"
            )

        original_filename = str(
            metadata.get(
                "original_filename",
                grid_out.filename or object_id,
            )
        )
        safe_filename = Path(original_filename).name

        if safe_filename in {"", ".", ".."}:
            raise ValueError("GridFS 文件名无效")

        DOWNLOAD_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        target = DOWNLOAD_DIR / safe_filename

        if target.exists():
            if not target.is_file():
                raise ValueError(
                    f"下载目标不是普通文件：{target}"
                )

            return {
                "file_id": str(object_id),
                "local_path": str(target.resolve()),
                "gridfs_size": int(grid_out.length),
                "downloaded_size": target.stat().st_size,
                "original_filename": safe_filename,
                "status": "文件已存在，未覆盖",
            }

        try:
            with target.open("xb") as output:
                while True:
                    chunk = grid_out.read(256 * 1024)

                    if not chunk:
                        break

                    output.write(chunk)
        except OSError as exc:
            if target.is_file():
                target.unlink()

            raise ValueError(
                f"文件写入失败：{exc}"
            ) from exc

        downloaded_size = target.stat().st_size

        self.audit.log_operation(
            operate_type="下载数字资源",
            target_collection="fs.files",
            target_id=str(object_id),
            operate_detail=(
                f"文件={safe_filename}, "
                f"保存路径={target.resolve()}, "
                f"字节数={downloaded_size}"
            ),
        )

        return {
            "file_id": str(object_id),
            "local_path": str(target.resolve()),
            "gridfs_size": int(grid_out.length),
            "downloaded_size": downloaded_size,
            "original_filename": safe_filename,
            "status": "下载成功",
        }

    def download_and_verify(
        self,
        file_id: str | ObjectId,
        original_path: str | Path | None = None,
    ) -> dict[str, Any]:
        object_id = self._parse_file_id(file_id)

        try:
            grid_out = self.fs.get(object_id)
        except NoFile as exc:
            raise ValueError(
                f"未找到 GridFS 文件：{object_id}"
            ) from exc

        metadata = grid_out.metadata or {}

        if metadata.get("file_type") != "ebook":
            raise ValueError("字节一致性校验仅用于电子书文件")

        if original_path is None:
            original_filename = str(
                metadata.get("original_filename", "")
            )
            source = RESOURCE_DIR / Path(
                original_filename
            ).name
        else:
            source = Path(original_path)

        if not source.is_file():
            raise ValueError(
                f"原始上传文件不存在：{source}"
            )

        download_result = self.download_file(
            object_id,
            required_type="ebook",
        )
        downloaded_path = Path(
            download_result["local_path"]
        )
        original_size = source.stat().st_size
        gridfs_size = int(grid_out.length)
        downloaded_size = downloaded_path.stat().st_size
        consistent = (
            original_size
            == gridfs_size
            == downloaded_size
        )

        return {
            "file_id": str(object_id),
            "original_path": str(source.resolve()),
            "local_path": str(downloaded_path.resolve()),
            "original_size": original_size,
            "gridfs_size": gridfs_size,
            "downloaded_size": downloaded_size,
            "consistent": consistent,
            "download_status": download_result["status"],
            "status": (
                "校验通过"
                if consistent
                else "校验失败"
            ),
        }
