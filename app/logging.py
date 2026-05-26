import logging
import os
import sys

from pythonjsonlogger import jsonlogger

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
        rename_fields = {'asctime': 'timestamp', 'levelname': 'level', 'name': 'logger'},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    root.handlers = []
    root.addHandler(handler)

    # logging.basicConfig(
    #     level=LOG_LEVEL,
    #     format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    #     handlers=[logging.StreamHandler(sys.stdout)],
    # )
