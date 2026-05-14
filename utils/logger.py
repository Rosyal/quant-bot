"""日志工具"""
import logging
import os
from config import LOG_LEVEL, LOG_PATH


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # 控制台
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        # 文件
        if LOG_PATH:
            os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
            fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
    return logger
