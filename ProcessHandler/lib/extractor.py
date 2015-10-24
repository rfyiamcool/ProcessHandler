# coding=utf-8

# -*- coding: utf-8 -*-

import time
import logging
import operator
import datetime
import traceback

from ProcessHandler.lib.utils import first
from ProcessHandler.lib.log import setup_logging,setup_file_logging
from ProcessHandler.lib.serialize import deserialize
from ProcessHandler.lib.workers.sync import SyncWorker

class Extractor(SyncWorker):

    LOGGER_NAME = "extractor"

    def __init__(self, cfg, file_logger=None, ppid=None, sockets=None):
        SyncWorker.__init__(self, cfg, file_logger, ppid)
        setup_file_logging(self.LOGGER_NAME, self.cfg.log_file)
        self.logger = logging.getLogger(self.LOGGER_NAME)

    def setup(self):
        super(Extractor, self).setup()

    def init_process(self):
        super(Extractor, self).init_process()

    def stop(self):
        super(Extractor, self).stop()

    def handle_request(self):
        while 1:
            print 123
            self.logger.info('123')
            time.sleep(3)

if __name__ == '__main__':
    pass
