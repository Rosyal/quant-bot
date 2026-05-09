"""
SQLite 冷备份: 复制 DB 文件到带时间戳的文件名.

用法:
  python scripts/db_backup.py
  python scripts/db_backup.py --dest-dir backups
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    import config as cfg

    p = argparse.ArgumentParser(description="备份 SQLite 数据库 (冷拷贝)")
    p.add_argument(
        "--dest-dir",
        default=os.path.join(root, "backups"),
        help="备份目录 (默认 项目根/backups)",
    )
    args = p.parse_args()
    src = os.path.abspath(cfg.DB_PATH)
    if not os.path.isfile(src):
        print(f"源库不存在: {src}")
        sys.exit(1)
    os.makedirs(args.dest_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(src).replace(".db", "")
    dst = os.path.join(args.dest_dir, f"{base}_{ts}.db")
    shutil.copy2(src, dst)
    print(f"已备份: {dst}")


if __name__ == "__main__":
    main()
