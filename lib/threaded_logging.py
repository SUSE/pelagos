import logging
import logging.config
import threading

log_prefix = '/tmp/'
thread_pelagos_log = None
thread_log_tmpl = ''
root_log_file = None
formatter = "%(asctime)-15s" \
            "| %(processName)-10s" \
            "| %(threadName)-11s" \
            "| %(levelname)-5s" \
            "| %(message)s"


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
    global thread_pelagos_log, thread_log_tmpl, root_log_file
    thread_pelagos_log = log_prefix + 'pelagos.log'
    thread_log_tmpl = log_prefix + 'pelagos_thrd_log-{}.log'
    root_log_file = log_prefix + 'pelagos_root.log'

    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'root_formatter': {
                'format': formatter
            }
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'root_formatter'
            },
            'log_file': {
                'class': 'logging.FileHandler',
                'level': 'DEBUG',
                'filename': root_log_file,
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
        }})


def get_log_name(thread_name):
    return thread_log_tmpl.format(thread_name)


def start(thread_name=None):
    if not thread_name:
        thread_name = threading.Thread.getName(
            threading.current_thread())
    logging.debug('New log name is:' +
                  thread_log_tmpl.format(thread_name))
    log_handler = logging.FileHandler(
            get_log_name(thread_name)
        )
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(
        logging.Formatter(formatter)
    )

    log_filter = ThreadedFilter(thread_name)
    log_handler.addFilter(log_filter)

    logging.getLogger().addHandler(log_handler)
    return log_handler


def stop(handler):
    if handler is None:
        return False
    logging.getLogger().removeHandler(handler)
    handler.flush()
    handler.close()
