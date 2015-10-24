#coding=utf-8
"""
# Simple leader/follower implemention base on gevent
"""
import os
import errno
import select
import socket
import traceback
import threading

import gevent
from gevent import getcurrent
from gevent.pool import Pool

from ProcessHandler.lib.workers.base import Worker
from ProcessHandler.lib.utils import close_on_exec

__all__ = ["CoroutineWorker"]

class CoroutineWorker(Worker):

    DEFAULT_GREENLET_SIZE = 10 # control the pool size

    def __init__(self, cfg, file_logger=None, ppid=None, sockets=None):
        super(CoroutineWorker, self).__init__(cfg, file_logger, ppid, sockets)
        self.max_greenlets = int(self.cfg.max_greenlets or self.DEFAULT_GREENLET_SIZE)

    def patch(self):
        from gevent import monkey
        monkey.noisy = False

        # if the new version is used make sure to patch subprocess
        if gevent.version_info[0] == 0:
            monkey.patch_all()
        else:
            monkey.patch_all(subprocess=True)

    def init_process(self):
        super(CoroutineWorker, self).init_process()
        self.patch()
        self.pool = Pool(self.max_greenlets)
        self.mutex = threading.Semaphore()
        self._stop_event = threading.Event()

    def run(self):
        super(CoroutineWorker, self).run()
        while self.alive:
            if not self.pool.full():
                self.pool.spawn(self._run)
            self.file_logger.debug("pool greenlet size %d" % (self.pool.size - self.pool.free_count()))
            gevent.sleep(1.0)

        self._stop_event.wait()
        gevent.spawn(self.stop).join()

    def _run(self):
        if self.LISTENERS:
            while self.alive:
                self.mutex.acquire()
                ret = select.select(self.rd_fds, [], [], 1.0)
                self.file_logger.debug("Before: socket fd length: %d, greenlet:%d, listen in:%s" % (len(self.rd_fds), id(getcurrent()), self.LISTENERS[0] in self.rd_fds))
                if ret[0]:
                    sock = ret[0][0]
                    self.rd_fds.remove(sock)
                else:
                    sock = None
                self.mutex.release()
                if sock:
                    #for sock in ret[0]:
                    if sock in self.LISTENERS:
                        try:
                            client, addr = sock.accept()
                            client.setblocking(0)
                            close_on_exec(client)
                            self.rd_fds.append(client)
                        except socket.error as e:
                            if e.args[0] not in (errno.EAGAIN, errno.EWOULDBLOCK,
                                         errno.ECONNABORTED):
                                self.file_logger.error(traceback.format_exc())

                        finally:
                            self.rd_fds.append(sock)
                    else:
                        r = self.handle_request(client=sock)
                        if r == -1:
                            sock.close()
                        else:
                            self.rd_fds.append(sock)

                if self.ppid and self.ppid != os.getppid():
                    self.file_logger.info("Parent changed, shutting down: %s", self)
                    return

        else:
            while self.alive:
                try:
                    self.handle_request()
                except:
                    self.file_logger.error(traceback.format_exc())

    def stop(self):
        Worker.stop(self)
        self.pool.join(timeout=1)

    def handle_quit(self, sig, frame):
        self.alive = False
        self._stop_event.set()
