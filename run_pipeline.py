import logging

from paper_radar.config import load_config
from paper_radar.db import init_db
from paper_radar.workflow import Pipeline

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def main():
    config = load_config()
    init_db(config.storage.db_path)
    pipeline = Pipeline(config)
    pipeline.run()


if __name__ == "__main__":
    main()
