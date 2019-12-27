import re

from .eventloop import Fd


SOCKET_READ_PORTION = 4096


class SocketClosedPrematurely(Exception):
    """Socket closed before the expected high-level message was consumed"""


def send_buffer(socket, buf):
    """Send any kind of buffer (e.g. bytes object, bytearray)"""
    mv = memoryview(buf)
    try:
        while mv:
            yield Fd.write(socket)
            n = socket.send(mv)
            mv, mv_old = mv[n:], mv
            mv_old.release()
    finally:
        mv.release()


def recv_up_to_delimiter(sock, buf, delimiter):
    """Precondition: buf must not already have a message

    :return: bytes object
    """
    while True:
        yield Fd.read(sock)
        chunk = sock.recv(SOCKET_READ_PORTION)
        if not chunk:
            raise SocketClosedPrematurely

        buf.extend(chunk)
        mo = re.search(delimiter, buf)
        if mo is not None:
            payload = bytes(buf[:mo.start()])
            del buf[:mo.end()]
            return payload


def recv_next(sock, buf, N):
    """Receive next N bytes from buffer"""
    return bytes((yield from recv_next_as_buf(sock, buf, N)))


def recv_next_as_buf(sock, buf, N):
    """Receive next N bytes from buffer as a bytearray object"""
    while len(buf) < N:
        yield Fd.read(sock)
        chunk = sock.recv(SOCKET_READ_PORTION)
        if not chunk:
            raise SocketClosedPrematurely

        buf.extend(chunk)

    new_buf = buf[:N]
    del buf[:N]
    return new_buf
