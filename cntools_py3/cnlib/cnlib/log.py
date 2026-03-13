#!/usr/bin/env python
"""
    import logging
    from cnlib import log
    logger = log.getLogger(__name__)

    def main():
        log.logfile("/path/to/file.log", console=False)
        log.file_handler.setLevel(logging.INFO)
        logger.debug("foo")
        logger.error("bar")

Probably best to configure the level, logfile, whatever at the beginning
of your main() function in case the module in question is later imported.
Submodules just need to get the logger and their messages
will go to the same place:

    from cnlib import log
    logger = log.getLogger(__name__)
    logger.info("module")

Logs to console by default if you don't call logfile(). If you want just the
file and no console output pass ", console=False" after the
path in the logfile() call.

The file is set up to support external logrotate by default. With parameters
it can be configured to rotate itself. Avoid self rotation with processes
which are not continuously running (cron jobs and web apps).

TODO could probably wrap all this up in a class and hopefully
keep it transparent to the user
"""

import logging
import logging.config
import logging.handlers

message_format = \
    "%(asctime)s.%(msecs)03d [%(levelname)s] " \
    "(%(process)d:%(thread)d:%(filename)s:%(lineno)s) %(message)s"
date_format = "%Y-%m-%dT%H:%M:%S"
formatter = None
console_handler = None
file_handler = None

root_name = 'cognet'

root_logger = logging.getLogger(root_name)
root_logger.setLevel(logging.INFO)


def set_format(message_format=message_format, date_format=date_format):
    global formatter
    formatter = logging.Formatter(fmt=message_format, datefmt=date_format)
    if console_handler is not None:
        console_handler.setFormatter(formatter)
    if file_handler is not None:
        file_handler.setFormatter(formatter)


def enable_console():
    global console_handler
    if console_handler is None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        if formatter is not None:
            console_handler.setFormatter(formatter)
        logging.getLogger('').addHandler(console_handler)


def disable_console():
    global console_handler
    if console_handler is not None:
        logging.getLogger('').removeHandler(console_handler)
        console_handler = None


def getLogger(name):
    return logging.getLogger('%s.%s' % (root_name, name))


def logfile(path, when=None, interval=1, backupCount=30,
            encoding=None, delay=False, utc=True, console=True):
    """Specify a log file where messages will be emitted.

    Calling this function replaces any previous log file.

    File rotation does not seem to work well for processes
    running under uwsgi or as cron jobs so this function is being
    altered to default to a WatchedFileHandler unless valid time
    parameters are passed. WatchedFileHandler will allow us
    to use a /etc/logrotate.d configuration to more generically
    handle log rotation.

    https://docs.python.org/2/library/logging.handlers.html
    """
    global file_handler
    with open(path, 'a') as f:
        # verify file is writeable or exception will be thrown
        pass
    if when is None:
        fh = logging.handlers.WatchedFileHandler(path, delay=delay)
    else:
        fh = logging.handlers.TimedRotatingFileHandler(
            path, when, interval, backupCount, encoding, delay, utc)
    fh.setLevel(logging.DEBUG)
    if formatter is not None:
        fh.setFormatter(formatter)
    logging.getLogger('').addHandler(fh)
    if console:
        enable_console()
    else:
        disable_console()
    if file_handler is not None:
        root_logger.removeHandler(file_handler)
    file_handler = fh


# SET UP DEFAULT STATE
set_format()
enable_console()

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    set_format(
        message_format="[%(levelname)s] (%(filename)s:%(lineno)s) %(message)s")

    logger.debug('debug message')
    logger.info('info message')
    logger.warning('warning message')

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
