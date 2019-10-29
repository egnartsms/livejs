"""Helpers: async Socket server and client, needed to test the Eventloop"""
import socket

from live.eventloop import get_event_loop, FdRead, FdWrite, is_fd


MSG_SEPARATOR = b'!end'


def send_all_data(socket, bytes_obj):
    mv = memoryview(bytes_obj)
    while mv:
        yield FdWrite(socket)
        n = socket.send(mv)
        mv = mv[n:]


def send_message(socket, str):
    yield from send_all_data(socket, str.encode('utf8') + MSG_SEPARATOR)


class StopServer(Exception):
    pass


def serve(port, word_processor, evt_up=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    sock.listen(5)

    if evt_up is not None:
        evt_up.set()

    try:
        while True:
            yield FdRead(sock)
            cli, address = sock.accept()
            get_event_loop().add_coroutine(client_handler(cli, word_processor))
    except StopServer:
        pass
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def client_handler(sock, word_processor):
    for val in read_delimited_strings(sock):
        if is_fd(val):
            yield val
            continue

        get_event_loop().add_coroutine(send_message(sock, word_processor(val)))


def read_delimited_strings(sock):
    """This is a coroutine that also yields non-fds"""
    buffer = bytearray()
    shutdown = False

    while True:
        if MSG_SEPARATOR in buffer:
            idx = buffer.index(MSG_SEPARATOR)
            word = bytes(buffer[:idx]).decode('utf8')
            del buffer[:idx + len(MSG_SEPARATOR)]
            yield word
        elif not shutdown:
            yield FdRead(sock)

            chunk = sock.recv(1024)
            buffer += chunk

            if not chunk:
                sock.shutdown(socket.SHUT_RD)
                shutdown = True
        else:
            sock.shutdown(socket.SHUT_WR)
            sock.close()
            break


# The Client

def connect(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    try:
        sock.connect(('127.0.0.1', port))
    except BlockingIOError:
        yield FdWrite(sock)
        return sock


def recv_1_response(sock):
    buffer = bytearray()
    while not buffer.endswith(MSG_SEPARATOR):
        yield FdRead(sock)

        chunk = sock.recv(1024)
        buffer += chunk

        if not chunk:
            raise RuntimeError("Server response ended prematurely")

    return buffer[:-len(MSG_SEPARATOR)].decode('utf8')


def recv_n_responses(sock, n):
    buffer = bytearray()
    res = []

    while len(res) < n:
        try:
            idx = buffer.index(MSG_SEPARATOR)
        except ValueError:
            pass
        else:
            word = buffer[:idx].decode('utf8')
            res.append(word)
            del buffer[:idx + len(MSG_SEPARATOR)]
            continue

        yield FdRead(sock)

        chunk = sock.recv(1024)
        buffer += chunk

        if not chunk:
            raise RuntimeError("Server response ended prematurely")

    return res