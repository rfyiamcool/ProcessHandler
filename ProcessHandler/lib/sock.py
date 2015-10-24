#coding=utf-8

import os
import socket

ALL_INTERFACE = '0.0.0.0'

def create_sockets(binds, unix_sock, backlog):
    """create listen sockets

    :Parameters:
      - `backlog`: listen queue max length
    """
    listeners = []
    if "OPEN_FD" in os.environ:
        fds = os.environ.pop("OPEN_FD").split(',')
        if binds:
            for i in range(len(binds)):
                listeners.append(_create_socket(binds[i], backlog, fds[i]))

        if unix_sock:
            listeners.append( _create_socket(unix_sock, backlog, socket.AF_UNIX, fds[-1]))

        return listeners

    if binds:
        """
        if ALL_INTERFACE in binds:
            listeners.append(_create_socket((ALL_INTERFACE, port), backlog)) # bind all interface
        else:
        """
        for bind in binds:
            listeners.append(_create_socket(bind, backlog))

    if unix_sock:
        sock = _create_socket(unix_sock, backlog, socket.AF_UNIX)
        listeners.append(sock)

    return listeners

def _create_socket(addr, backlog, socket_family=socket.AF_INET, fd=None):
    if fd:
        sock = socket.fromfd(fd, socket_family, socket.SOCK_STREAM)
    else:
        sock = socket.socket(socket_family, socket.SOCK_STREAM)
    set_socket_options(sock)
    sock.bind(addr)
    sock.listen(backlog)
    return sock

def set_socket_options(sock):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #if sock.family == sock.AF_INET:
    #    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.setblocking(0)
