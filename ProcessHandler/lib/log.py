#coding=utf-8
import os
import socket
import logging
from logging.config import fileConfig


class Utf8Logger(logging.Logger):
    def _log(self, level, msg, args, exc_info=None, extra=None):
        if args:
            args = tuple([arg.encode('utf-8') if isinstance(arg, unicode) else arg for arg in args])
        logging.Logger._log(self, level, msg, args, exc_info, extra)

def setup_logging(conf_file_name):
    logging.setLoggerClass(Utf8Logger)
    fileConfig(conf_file_name, dict(__file__=conf_file_name, here=os.path.dirname(conf_file_name)), disable_existing_loggers=0)

DEFAULT_FORMAT = '[%(asctime)s] %(levelname)s jobexecute "%(message)s"'

def setup_file_logging(logger_name, file_name, level=logging.INFO, log_format=DEFAULT_FORMAT, propagate=0):
    logger_name = 'jobexecute'
    file_name = 'master.log'
    logger = logging.getLogger(None if logger_name == "root" else logger_name)
    logger.propagate = propagate
    logger.setLevel(level)
    fh = logging.FileHandler(file_name)
    fh.setLevel(level)
    formatter = logging.Formatter(log_format)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger

if __name__ == "__main__":
    logger = setup_file_logging('jobexecute','master.log')
    logger.info('main')
