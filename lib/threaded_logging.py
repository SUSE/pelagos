import logging
import logging.config
import threading

thread_pelagos_log = '/tmp/pelagos.log'
thread_log_tmpl = '/tmp/pelagos_thrd_log-{}.log'


class ThreadedFilter(logging.Filter):
    """
    This filter only show log entries for specified thread name
    """

    def __init__(self, thread_name, *args, **kwargs):
        logging.Filter.__init__(self, *args, **kwargs)
        self.thread_name = thread_name

    def filter(self, record):
        return record.threadName == self.thread_name


def config_root_logger():
    log_file = '/tmp/perThreadLogging.log'

    formatter = "%(asctime)-15s" \
                "| %(processName)-10s" \
                "| %(threadName)-11s" \
                "| %(levelname)-5s" \
                "| %(message)s"

    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'root_formatter': {
                'format': formatter
            }
        },
        'handlers': {
            'console': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'root_formatter'
            },
            'log_file': {
                'class': 'logging.FileHandler',
                'level': 'DEBUG',
                'filename': log_file,
                'formatter': 'root_formatter',
            }
        },
        'loggers': {
            '': {
                'handlers': [
                    'console',
                    'log_file',
                ],
                'level': 'DEBUG',
                'propagate': True
            }
        }
    })


def start(thread_name=None):
    if thread_name is not None:
        thread_name = threading.Thread.getName(
            threading.current_thread())

    log_handler = logging.FileHandler(
            thread_log_tmpl.format(thread_name)
        )
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(
        logging.Formatter(
            "%(asctime)-15s"
            "| %(threadName)-11s"
            "| %(levelname)-5s"
            "| %(message)s"
        )
    )

    log_filter = ThreadedFilter(thread_name)
    log_handler.addFilter(log_filter)

    logging.getLogger().addHandler(log_handler)
    # data = threading.local()
    # pxelinux_cfg.thread_local = thread_logger

    return log_handler
