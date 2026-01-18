import logging
import os
import sys

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


def setup_logging():
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )
