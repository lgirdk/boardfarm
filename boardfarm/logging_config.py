import logging
import logging.config

logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {"bft_fmt": {"format": "%(message)s"}},
        "handlers": {
            "console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "bft_fmt",
            },
        },
        "loggers": {
            "zeep.transports": {
                "level": "DEBUG",
                "propagate": False,
                "handlers": ["console"],
            },
            "bft": {"level": "DEBUG", "propagate": False, "handlers": ["console"]},
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
