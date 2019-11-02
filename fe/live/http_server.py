"""Home-made asynchronous HTTP server"""
import socket
import re
import os
import mmap

from live.eventloop import FdRead, FdWrite, get_event_loop


def serve(port, be_root):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    sock.listen(5)

    try:
        while True:
            yield FdRead(sock)
            cli, address = sock.accept()
            co = handle_http_request_wrapper(cli, be_root)
            co.send(None)
            get_event_loop().add_coroutine(co)
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request_wrapper(sock, be_root):
    """Make sure sock is properly closed"""
    try:
        yield None
        return (yield from handle_http_request(sock, be_root))
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request(sock, be_root):
    buf = bytearray()
    stop = False

    while not stop:
        header = yield from recv_up_to_delimiter(sock, buf, b'\r\n\r\n')
        if header is None:
            break

        req = Request.from_network(header)
        resp = Response(sock, req.protocol)

        stop = req.headers.get('connection') != 'keep-alive'

        if req.path == '/':
            filename = 'page.html'
        else:
            filename = req.path[1:]

        filepath = os.path.join(be_root, filename)
        if not os.path.exists(filepath):
            yield from resp.send_404()
            continue

        if filename.endswith('.js'):
            mimetype = 'application/javascript'
        elif filename.endswith('.html'):
            mimetype = 'text/html'
        elif filename.endswith('.css'):
            mimetype = 'text/css'
        else:
            mimetype = 'text/plain'

        yield from resp.send_file(filepath, mimetype)


def recv_up_to_delimiter(sock, buf, delimiter):
    """Precondition: buf must not already have a message"""
    while True:
        yield FdRead(sock)
        chunk = sock.recv(4096)
        if not chunk:
            return None

        buf.extend(chunk)
        mo = re.search(delimiter, buf)
        if mo is not None:
            msg = bytes(buf[:mo.start()])
            del buf[:mo.end()]
            return msg


def send_buffer(socket, buf):
    """Send any kind of immutable buffer (e.g. bytes object but not bytearray)"""
    mv = memoryview(buf)
    while mv:
        yield FdWrite(socket)
        n = socket.send(mv)
        mv = mv[n:]


def send_str(socket, str):
    yield from send_buffer(socket, str.encode('ascii'))


class Request:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    @classmethod
    def from_network(cls, bytes_obj):
        status_line, *http_headers = bytes_obj.split(b'\r\n')
        method, path, protocol = status_line.split()

        parsed_headers = {}
        for http_header in http_headers:
            i = http_header.index(b':')
            header_name = http_header[:i]
            header_value = http_header[i + 1:].strip()
            header_name = header_name.decode('ascii').lower()
            header_value = header_value.decode('ascii')
            parsed_headers[header_name] = header_value

        return cls(
            method=method.decode('ascii'),
            path=path.decode('ascii'),
            protocol=protocol,
            headers=parsed_headers
        )


class Response:
    def __init__(self, sock, protocol):
        self.sock = sock
        self.protocol = protocol

    def _status_line(self, code):
        return '{} {} NP'.format(self.protocol, code).encode('ascii')

    def _header(self, name, value):
        return '{}: {}'.format(name, value).encode('ascii')

    def send_file(self, filepath, mimetype):
        pieces = []
        pieces.append(self._status_line(200))

        fd = os.open(filepath, os.O_RDONLY)
        try:
            with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as fmap:
                pieces.append(self._header('Content-Length', len(fmap)))
                pieces.append(self._header('Content-Type', mimetype))
                pieces.append(b'\r\n')
                yield from send_buffer(self.sock, b'\r\n'.join(pieces))
                yield from send_buffer(self.sock, fmap)
        finally:
            os.close(fd)

    def send_404(self):
        pieces = []
        pieces.append(self._status_line(404))
        pieces.append(self._header('Content-Length', 0))
        pieces.append(b'\r\n')
        yield from send_buffer(self.sock, b'\r\n'.join(pieces))
