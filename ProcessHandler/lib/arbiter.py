#coding=utf-8

# This module implement prefork model,  used for spawn and manage child process
import os
import sys
import time
import errno
import signal
import random
import select
import traceback

from ProcessHandler.lib.pidfile import Pidfile
from ProcessHandler.lib.config import Config
from ProcessHandler.lib.errors import HaltServer
from ProcessHandler.lib.sock import create_sockets
from ProcessHandler.lib.log import setup_file_logging
from ProcessHandler.lib.utils import (getcwd, daemonize, set_non_blocking, close_on_exec,
                            reopen_log_file, _setproctitle, set_process_owner, chown,
                            str2bool, get_user_info, import_app, reopen_log_file)

logger = setup_file_logging('extractor','extractor.log')

class Arbiter(object):

    PIPE = []
    START_CTX = {} # for exec
    LISTENERS = [] # listening sockets
    WORKERS = {}
    WORKER_BOOT_ERROR = 3
    SOCK_BACKLOG = 20

    # signals
    SIG_QUEUE = []
    SIGNALS = [getattr(signal, "SIG%s" % x) \
            for x in "HUP QUIT INT TERM TTIN TTOU USR1 USR2 WINCH".split()]
    SIG_NAMES = dict(
        (getattr(signal, name), name[3:].lower()) for name in dir(signal)
        if name[:3] == "SIG" and name[3] != "_"
    )

    def __init__(self, worker_uri, config_file=None, section=None):
        self.worker_uri = worker_uri
        self.config_file = config_file
        self.section = section

        self.reexec_pid = 0
        self.worker_age = 0
        self.setup()

        # init start context
        cwd = getcwd()
        #self.master_name = "Master"
        args = sys.argv[:]
        args.insert(0, sys.executable)

        self.START_CTX = {
            "args": args,
            "cwd": cwd,
            0: sys.executable
        }

        self.worker_boot_time = time.time()

    def setup(self):
        # load config file
        if self.config_file:
            Config.ACTUAL_CONFIG_FILE = self.config_file
        else:
            self.config_file = Config.DEFAULT_CONFIG_FILE

        if self.section:
            Config.SECTION_NAME = self.section

        self.cfg = Config()

        if isinstance(self.cfg.daemonize, basestring):
            self.daemonize = str2bool(self.cfg.daemonize)

        if self.cfg.log_file is not None:
            self.log_file = self.cfg.log_file

        if self.cfg.pidfile is not None:
            self.pidfile = Pidfile(self.cfg.pidfile)

        self.master_name = "master: %s" % self.cfg.proc_name
        if self.cfg.number_workers:
            self.number_workers = int(self.cfg.number_workers)

        if self.cfg.graceful_timeout:
            self.graceful_timeout = float(self.cfg.graceful_timeout)

        if self.cfg.user:
            user = self.cfg.user.split(':')
            if len(user) <= 1:
                user[1] = user[0]
            self.uid, self.gid = get_user_info(*user[:2])
        else:
            # set as default
            self.uid, self.gid = os.getuid(), os.getgid()

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

        if self.cfg.kill_interval:
            self.kill_interval = int(self.cfg.kill_interval)
        else:
            self.kill_interval = 0

    def __getattr__(self, name):
        value = getattr(self.cfg, name)
        if value is None:
            self.file_logger.warning('No config option %s' % name)

        return value

    @property
    def worker_class(self):
        """
        lazy load after fork
        """
        return import_app(self.worker_uri)

    def init_signals(self):
        """\
        Initialize master signal handling. Most of the signals
        are queued. Child signals only wake up the master.
        """
        [signal.signal(s, self.signal) for s in self.SIGNALS]
        signal.signal(signal.SIGCHLD, self.handle_chld)

    def start(self):
        # Initialize the arbiter, create pidfile if needed.
        self.set_process_owner(self.uid, self.gid)

        # setup logging
        self.file_logger = setup_file_logging("prefork", self.log_file)
        self.file_logger.info("Startting arbiter")
        self.file_logger.info('Use Config File %s', self.config_file)

        if self.daemonize:
            daemonize()

        _setproctitle(self.master_name)
        self.pid = os.getpid()
        logger.info("%s"%self.pid)
        try:
            if self.pidfile:
                self.pidfile.create(self.pid)
                # chown(self.pidfile.fname, self.uid, self.gid)
        except Exception,e:
            logger.info(str(e))

        self.init_signals()

        # close old PIPE on reexec
        if self.PIPE:
            [os.close(p) for p in self.PIPE]

        # initialize the pipe
        self.PIPE = pair = os.pipe()
        for p in pair:
            set_non_blocking(p)
            close_on_exec(p)

        if not self.LISTENERS and (self.bind or self.unix_socket):
            self.file_logger.info("Listern on %s, unixdomian:%s", self.cfg.bind or "", self.cfg.unix_socket or "")
            self.LISTENERS = create_sockets(self.bind, self.unix_socket, self.SOCK_BACKLOG)

        for s in self.LISTENERS:
            close_on_exec(s)
            s.setblocking(0)

    def run(self):
        self.start()
        self.manage_workers()
        while 1: # handle signals and manage worker process
            try:
                self.reap_workers()
                sig = self.SIG_QUEUE.pop(0) if len(self.SIG_QUEUE) else None
                if sig is None:
                    self.sleep()
                    if self.kill_interval and time.time() > (self.worker_boot_time + self.kill_interval):
                        self.stop()
                        self.worker_boot_time = time.time()
                    self.manage_workers()
                    continue
                if sig not in self.SIG_NAMES:
                    self.file_logger.info("Ignoring unknown signal: %s", sig)
                    continue
                signame = self.SIG_NAMES.get(sig)
                print signame
                handler = getattr(self, "handle_%s" % signame, None)
                if not handler:
                    self.file_logger.error("Unhandled signal: %s", signame)
                    continue
                self.file_logger.info("Handling signal: %s", signame)
                handler()
            #except StopIteration:
            #    self.halt()
            except KeyboardInterrupt:
                self.halt()
            except HaltServer as inst:
                self.halt(reason=inst.reason, exit_status=inst.exit_status)
            except SystemExit:
                raise
            except Exception:
                self.file_logger.info("Unhandled exception in main loop:\n%s",
                            traceback.format_exc())
                self.stop(False)
                if self.pidfile is not None:
                    self.pidfile.unlink()
                sys.exit(-1)

    def manage_workers(self):
        """\
        Maintain the number of worders by spawning or killing as required
        """
        actual_number_workers = len(self.WORKERS.keys())
        if actual_number_workers < self.number_workers:
            self.spawn_workers()
        else:
            if actual_number_workers > self.number_workers:
                workers = sorted(self.WORKERS.items(), key=lambda x: x[1]) # age, bigger means newer
                pids = [pid for pid, _ in workers[:actual_number_workers - self.number_workers]]
                self.file_logger.info("kill pids:%s", pids)
                self.kill_workers(pids)

    def spawn_workers(self):
        for i in range(self.number_workers - len(self.WORKERS.keys())):
            self.spawn_worker()
            time.sleep(0.1 * random.random())

    def spawn_worker(self):
        self.worker_age += 1
        pid = os.fork()
        if pid != 0: # parent
            self.WORKERS[pid] = self.worker_age # need worker's age param
            # self.file_logger.info("add pid:%s", pid)
            return pid
        # process child
        try:
            worker = self.worker_class(self.cfg, self.file_logger, self.pid, self.LISTENERS)
            worker_pid = os.getpid()
            self.file_logger.info("Booting worker with pid:%s", worker_pid)
            self.set_process_owner(self.uid, self.gid)
            
            worker.run()
            sys.exit(0)
        except SystemExit:
            raise
        except:
            self.file_logger.exception("Exception in worker process:\n%s", traceback.format_exc())
            if not worker.booted:
                sys.exit(self.WORKER_BOOT_ERROR)
            sys.exit(-1)
        finally:
            self.file_logger.info("Worker exiting (pid: %s)", worker_pid)

    def kill_workers(self, pids, sig=signal.SIGQUIT):
        for pid in pids:
            self.kill_worker(pid, sig)

    def kill_worker(self, pid, sig=signal.SIGQUIT):
        try:
            os.kill(pid, sig)
        except OSError as e:
            if e.errno == errno.ESRCH:
                try:
                    worker = self.WORKERS.pop(pid)
                except (KeyError, OSError):
                    return
            else:
                raise e

    def reap_workers(self):
        """\
        Reap workers to avoid zombie processes
        """
        try:
            while 1:
                wpid, status = os.waitpid(-1, os.WNOHANG) # -1 means wait for any child of the current process, see doc:http://docs.python.org/2/library/os.html
                if not wpid:
                    break
                self.file_logger.info("Reap worker %s", wpid)
                if self.reexec_pid == wpid:
                    self.reexec_pid = 0
                else:
                    exitcode = status >> 8
                    if exitcode == self.WORKER_BOOT_ERROR:
                        reason = "Worker failed to boot."
                        raise HaltServer(reason, self.WORKER_BOOT_ERROR)
                    worker = self.WORKERS.pop(wpid, None)
                    if not worker:
                        continue
        except OSError as e:
            if e.errno == errno.ECHILD:
                pass

    def sleep(self):
        """\
        Sleep until PIPE is readable or we timeout.  A readable PIPE means a signal occurred.
        """
        try:
            ready = select.select([self.PIPE[0]], [], [], 1.0)
            if not ready[0]:
                return
            while os.read(self.PIPE[0], 1):
                pass
        except select.error as e:
            if e.args[0] not in [errno.EAGAIN, errno.EINTR]:
                raise
        except OSError as e:
            if e.errno not in [errno.EAGAIN, errno.EINTR]:
                raise
        except KeyboardInterrupt:
            sys.exit()

    def wakeup(self):
        """\
        Wake up the arbiter by writing to the PIPE
        """
        try:
            os.write(self.PIPE[1], b'.')
        except IOError as e:
            if e.errno not in [errno.EAGAIN, errno.EINTR]:
                raise

    def halt(self, reason=None, exit_status=0, graceful=True):
        """ halt arbiter """
        self.stop()
        self.file_logger.info("Shutting down: %s", self.master_name)
        if reason is not None:
            self.file_logger.info("Reason: %s", reason)
        if self.pidfile is not None:
            self.pidfile.unlink()

        if self.unix_socket:
            os.unlink(self.unix_socket)

        sys.exit(exit_status)

    def stop(self, graceful=True):
        """
        kill worker graceful or not
        """
        # self.LISTENERS = []
        sig = signal.SIGQUIT if graceful else signal.SIGTERM
        limit = time.time() + self.graceful_timeout
        while self.WORKERS and time.time() < limit:
            self.kill_workers(self.WORKERS.keys(), sig)
            time.sleep(0.1)
            self.reap_workers()
        self.kill_workers(self.WORKERS.keys(), signal.SIGKILL) # force quit after gracefull timeout

    def reload(self):
        self.file_logger.info("Reload config file:%s", self.cfg.ACTUAL_CONFIG_FILE)

        old_pidfile = self.pidfile
        self.cfg.load_config()
        self.setup()

        if old_pidfile and self.pidfile and old_pidfile.fname != self.pidfile.fname:
            #old_pidfile.unlink()
            self.file_logger.info("pidfile:%s", self.pidfile.fname)
            self.pidfile.rename(self.pid)

        self.set_process_owner(self.uid, self.gid)
        self.file_logger = setup_file_logging("prefork", self.log_file)
        _setproctitle(self.master_name)

        # start new workers
        for i in range(self.number_workers):
            self.spawn_worker()

        self.manage_workers()

    def reexec(self):
        """
        Relaunch the master and workers.
        """
        if self.pidfile is not None:
            self.pidfile.rename("%s.oldbin" % self.pidfile.fname)
        self.reexec_pid = os.fork()
        if self.reexec_pid != 0:
            self.master_name = "Old %s" % self.master_name
            _setproctitle(self.master_name)
            return

        os.chdir(self.START_CTX['cwd'])
        os.execvpe(self.START_CTX[0], self.START_CTX['args'], os.environ)

    def set_process_owner(self, uid, gid):
        try:
            set_process_owner(uid, gid)
        except OSError as e:
            if e.errno == errno.EPERM:
                self.file_logger.warning("Set proc username need sudo permission, use default user instead")
            else:
                raise e

    def signal(self, sig, frame):
        if len(self.SIG_QUEUE) < 5:
            self.SIG_QUEUE.append(sig)
            self.wakeup()

    def handle_chld(self, sig, frame):
        "handle SIGCHLD"
        self.wakeup()

    def handle_quit(self):
        "SIGQUIT handling"
        self.halt()

    def handle_int(self):
        "SIGINT handling"
        self.halt(graceful=False)

    def handle_term(self):
        "SIGTERM handling"
        self.halt(graceful=False)

    def handle_hup(self):
        """\
        HUP handling.
        - Reload configuration
        - Start the new worker processes with a new configuration
        - Gracefully shutdown the old worker processes
        """
        self.file_logger.info("Hang up: %s", self.master_name)
        self.reload()

    def handle_winch(self):
        "SIGWINCH handling, gracefully stop workers"
        if self.daemonize:
            self.file_logger.info("graceful stop of workers")
            self.number_workers = 0
            self.kill_workers(self.WORKERS.keys(), signal.SIGQUIT)
        else:
            self.file_logger.info("SIGWINCH ignored. Not daemonized")


    def handle_ttin(self):
        """\
        SIGTTIN handling.
        Increases the number of workers by one.
        """
        self.number_workers += 1
        self.manage_workers()

    def handle_ttou(self):
        """\
        SIGTTOU handling.
        Decreases the number of workers by one.
        """
        if self.number_workers <= 1:
            return
        self.number_workers -= 1
        self.manage_workers()

    def handle_usr1(self):
        """\
        SIGUSR1 handling.
        Reload log file by sending them a SIGUSR1
        """
        self.kill_workers(self.WORKERS.keys(), signal.SIGUSR1)
        reopen_log_file(self.file_logger)

    def handle_usr2(self):
        """\
        SIGUSR2 handling.
        Creates a new master/worker set as a slave of the current
        master without affecting old workers. Use this to do live
        deployment with the ability to backout a change.
        """
        self.reexec()
        self.kill_workers(self.WORKERS.keys(), signal.SIGUSR2)
