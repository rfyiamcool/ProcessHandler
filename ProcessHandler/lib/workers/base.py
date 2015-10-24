#coding=utf-8

import os
import signal
import logging

from ProcessHandler.lib.utils import close_on_exec
from ProcessHandler.lib.sock import create_sockets
from ProcessHandler.lib.utils import _setproctitle, reopen_log_file

MAXSIZE = (1 << 31) - 1

class Worker(object):

    SIGNALS = [getattr(signal, "SIG%s" % x) \
               for x in "HUP QUIT INT TERM USR1 USR2 WINCH CHLD".split()]


    SOCK_BACKLOG = 20

    def __init__(self, cfg, file_logger, ppid, sockets=None):
        self.cfg = cfg
        self.file_logger = file_logger or logging.getLogger()
        self.ppid = ppid
        self.LISTENERS = sockets

        self.alive = True
        self.booted = False
        self.worker_name = "worker: %s" % cfg.proc_name
        self.nr = 0 # actual handle request count
        self.max_requests = int(self.cfg.max_requests or MAXSIZE)
        self.rd_fds = None

    @property
    def pid(self):
        return os.getpid()

    def __str__(self):
        return "<Worker %s>" % self.pid

    def init_signals(self):
        [signal.signal(s, signal.SIG_DFL) for s in self.SIGNALS]
        # init new signaling
        signal.signal(signal.SIGQUIT, self.handle_quit)
        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGWINCH, self.handle_winch)
        signal.signal(signal.SIGUSR1, self.handle_usr1)
        # Don't let SIGQUIT and SIGUSR1 disturb active requests
        # by interrupting system calls
        if hasattr(signal, 'siginterrupt'):  # python >= 2.6
            signal.siginterrupt(signal.SIGQUIT, False)
            signal.siginterrupt(signal.SIGUSR1, False)

    def setup(self):
        if self.cfg.bind:
            binds = []
            for b in self.cfg.bind.split(','):
                addr = b.strip().split(':')
                binds.append((addr[0], int(addr[1])))
            self.bind = binds
            # self.bind = [tuple(b.strip().split(":")) for b in self.cfg.bind.split(',')] # bind address comma separate
        else:
            self.bind = None
        self.unix_socket = self.cfg.unix_socket

    def init_process(self):
        self.setup()

        #set proc name
        _setproctitle(self.worker_name)
        self.init_signals()

        # bind ip and port if needed
        if not self.LISTENERS and (self.bind or self.unix_socket):
            self.file_logger.info("Listern on %s, unixdomian:%s", self.cfg.bind or "", self.cfg.unix_socket or "")
            self.LISTENERS = create_sockets(self.bind, self.unix_socket, self.SOCK_BACKLOG)

        if self.LISTENERS:
            for s in self.LISTENERS:
                close_on_exec(s)
                s.setblocking(0)

            self.rd_fds = list(self.LISTENERS)
        else:
            self.rd_fds = None
        # enter main loop
        self.booted = True

    def run(self):
        self.init_process()

    def handle_request(self, sock=None, client=None, addr=None):
        raise NotImplementedError()

    def stop(self):
        self.alive = False
        if self.LISTENERS:
            for l in self.LISTENERS:
                l.close()

    def handle_quit(self, sig, frame):
        self.stop()

    def handle_exit(self, sig, frame):
        self.alive = False
        os._exit(0)

    def handle_winch(self, sig, frame):
        return

    def handle_usr1(self, sig, frame):
        reopen_log_file(self.file_logger)

    def handle_usr2(self, sig, frame):
        pass

        """
        fds = [l.fileno() for l in self.LISTENERS]
        os.environ['OPEN_FD'] = ",".join([str(fd) for fd in fds])
        """

    """
    def reload(self):

        # config listeners
        old_bind = self.bind
        old_sock = self.unix_socket
        old_port = self.port

        if self.port != old_port or self.bind != old_bind or self.unix_socket != old_sock: # ugly
            [sock.close() for sock in self.LISTENERS]
            self.LISTENERS = create_sockets(self.bind, self.port, self.unix_socket, self.backlog or 20)
    """
