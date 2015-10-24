# coding=utf-8

import time
import logging
import traceback

from ProcessHandler.lib.log import setup_file_logging
from ProcessHandler.lib.workers.sync import SyncWorker

logger = setup_file_logging('jobexecute','master.log')
class JobExecute(SyncWorker):

    LOGGER_NAME = "jobexecute"

    def __init__(self, cfg, file_logger=None, ppid=None, sockets=None):
        SyncWorker.__init__(self, cfg, file_logger, ppid)
#        setup_file_logging(self.LOGGER_NAME, self.cfg.log_file)
#        self.logger = logging.getLogger(self.LOGGER_NAME)

    def setup(self):
        super(JobExecute, self).setup()

    def init_process(self):
        super(JobExecute, self).init_process()

    def stop(self):
        super(JobExecute, self).stop()

    def handle_request(self):
        while 1:
            print 'go....'
            logger.info('go...')
            time.sleep(1.5)

if __name__ == '__main__':
    pass
