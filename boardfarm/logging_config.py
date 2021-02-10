import logging
import logging.config

logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "bft_fmt": {"format": "%(message)s"},
            "tests_fmt": {"format": "%(asctime)s %(levelname)s %(message)s"},
        },
        "handlers": {
            "console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "bft_fmt",
            },
            "console_bf_logger": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "tests_fmt",
            },
        },
        "loggers": {
            "zeep.transports": {
                "level": "DEBUG",
                "propagate": True,
                "handlers": ["console_bf_logger"],
            },
            "bft": {"level": "DEBUG", "propagate": False, "handlers": ["console"]},
            "tests_logger": {
                "level": "INFO",
                "propagate": False,
                "handlers": ["console_bf_logger"],
            },
            "DeviceManager": {
                "level": "INFO",
                "propagate": False,
                "handlers": ["console"],
            },
            "elk-reporter": {
                "level": "DEBUG",
                "propagate": False,
                "handlers": ["console"],
            },
        },
    }
)
# DEBUG, INFO, WARNING, ERROR, CRITICAL
logger = logging.getLogger("bft")
