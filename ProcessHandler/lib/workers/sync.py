#coding=utf-8

import os
import errno
import socket
import select

from ProcessHandler.lib.utils import close_on_exec
from ProcessHandler.lib.workers.base import Worker

__all__ = ["SyncWorker"]

class SyncWorker(Worker):

    def run(self):
        super(SyncWorker, self).run()
        if self.LISTENERS:
            while self.alive:
                ret = select.select(self.rd_fds, [], [], 1.0)
                if ret[0]:
                    try:
                        for sock in ret[0]:
                            client, addr = sock.accept()
                            client.setblocking(1)
                            close_on_exec(client)
                            self.handle_request(sock, client, addr)

                    except socket.error as e:
                        if e.args[0] not in (errno.EAGAIN, errno.ECONNABORTED,
                                errno.EWOULDBLOCK):

                            client.close()
                            self.rd_fds.remove(client)

                if self.ppid != os.getppid():
                    self.file_logger.info("Parent changed, shutting down: %s", self)
                    return

                self.nr += 1
                if self.nr > self.max_requests:
                    self.alive = False

        else:
            while self.alive:
                self.handle_request()
                self.nr += 1
                if self.nr > self.max_requests:
                    self.alive = False
