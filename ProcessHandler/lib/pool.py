#coding=utf-8

import time
import threading

class ConnectionPool(object):

    def __init__(self, connection_class, args, kwargs=None, max_size=5):
        self.connection_class = connection_class
        self._args = args
        self._kwargs = kwargs
        self.max_size = max_size
        self._size = 0
        self.active_count = 0
        # self._mutex = threading.RLock()
        self._mutex = threading.Semaphore()
        self.conn = []

    def _make_connection(self):
        # self._mutex.acquire()
        if self._kwargs:
            conn = self.connection_class(*self._args, **self._kwargs)
        else:
            conn = self.connection_class(*self._args)

        # self.conn.append(conn)
        self._size += 1
        self.active_count += 1
        # self._mutex.release()
        return conn

    def get(self, retry_times=5):
        conn = None
        while retry_times:
            self._mutex.acquire()
            try:
                conn = self.conn.pop()
            except IndexError as e:
                if self.max_size > self._size:
                    conn = self._make_connection()
            finally:
                self._mutex.release()

            if conn is not None:
                break

            retry_times -= 1
            time.sleep(0.0001)

        return conn

    def release(self, conn):
        if isinstance(conn, self.connection_class):
            self._mutex.acquire()
            self.conn.append(conn)
            self.active_count -= 1
            self._mutex.release()

    def disconnect(self):
        for conn in self.conn:
            conn.close()

    def decrease(self):
        self._mutex.acquire()
        self._size -= 1
        self.active_count -= 1
        self._mutex.release()

    def close(self):
        self.disconnect()
