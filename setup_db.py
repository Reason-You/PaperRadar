"""初始化 SQLite 数据库表结构"""

from paper_radar.config import load_config
from paper_radar.db import init_db, upsert_conference


def main():
    config = load_config()
    init_db(config.storage.db_path)
    for conf in config.conferences:
        upsert_conference(config.storage.db_path, conf.name, conf.year)
    print(f"数据库已初始化并写入会议列表 -> {config.storage.db_path}")


if __name__ == "__main__":
    main()
