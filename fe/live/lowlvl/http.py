import mmap
import re
import os
import http.client

from .eventloop import Fd
from .sockutil import send_buffer


class Request:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    @classmethod
    def from_network(cls, sock, headers):
        status_line, *http_headers = headers.split(b'\r\n')
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
            sock=sock,
            method=method.decode('ascii'),
            path=path.decode('ascii'),
            protocol=protocol.decode('ascii'),
            headers=parsed_headers
        )


class Response:
    def __init__(self, req, status_code):
        self.sock = req.sock
        self.protocol = req.protocol
        self.headers = [
            (b'Server', b'Sublime 3 plug-in webserver')
        ]
        self.status_code = status_code
    
    def _status_line(self):
        return '{} {} {}'.format(self.protocol, self.status_code,
                                 http.client.responses[self.status_code]).encode('ascii')

    def add_header(self, name, value):
        self.headers.append((ensure_encoded(name), ensure_encoded(value)))

    def collect_headers(self):
        pieces = []
        pieces.append(self._status_line())
        for name, value in self.headers:
            pieces.append(b''.join([name, b': ', value]))
        pieces.append(b'\r\n')
        return b'\r\n'.join(pieces)
 
    def send_file(self, filepath):
        fd = os.open(filepath, os.O_RDONLY)
        try:
            with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as fmap:
                self.add_header('Content-Length', str(len(fmap)))
                self.add_header('Content-Type', mimetype_of(filepath))
                yield from send_buffer(self.sock, self.collect_headers())
                yield from send_buffer(self.sock, fmap)
        finally:
            os.close(fd)

    def send_empty(self):
        self.add_header('Content-Length', '0')
        yield from send_buffer(self.sock, self.collect_headers())


def ensure_encoded(obj):
    if isinstance(obj, bytes):
        return obj
    else:
        return obj.encode('ascii')


def mimetype_of(filename):
    if filename.endswith('.js'):
        return 'application/javascript'
    elif filename.endswith('.html'):
        return 'text/html'
    elif filename.endswith('.css'):
        return 'text/css'
    else:
        return 'text/plain'
