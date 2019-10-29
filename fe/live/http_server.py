"""Home-made asynchronous HTTP server"""
import socket
import re

from live.eventloop import FdRead, FdWrite, get_event_loop


class StopServer(Exception):
    pass


def serve(port, ):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    sock.listen(5)

    try:
        while True:
            yield FdRead(sock)
            cli, address = sock.accept()
            get_event_loop().add_coroutine(handle_http_request(cli))
    except StopServer:
        pass
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request(sock):
    buf = bytearray()

    header = yield from recv_up_to_delimiter(sock, buf, b'\r\n\r\n')
    request = parse_request_header(header)
    res = []
    for name, value in request.headers.items():
        res.append('<li>{}: {}</li>'.format(name, value))
    # print("path=", request.path, "method=", request.method, "headers=", request.headers)
    yield from send_all_data(sock, '{proto} 200 OK\r\n\r\n'.format(proto=request.proto))
    yield from send_all_data(sock, '''
    <html>
    <body>
      <p>{method} {path}</p>
      <ul>
          {headers}
      </ul>
    </body>
    </html>
    '''.format(method=request.method, path=request.path, headers='\n'.join(res)))
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()


def recv_up_to_delimiter(sock, buf, delimiter):
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


def send_all_data(socket, obj):
    if isinstance(obj, str):
        bytes_obj = obj.encode('utf8')
    else:
        bytes_obj = obj

    mv = memoryview(bytes_obj)
    while mv:
        yield FdWrite(socket)
        n = socket.send(mv)
        mv = mv[n:]


def parse_request_header(header):
    status_line, *http_headers = header.split(b'\r\n')
    method, path, proto = status_line.split()

    parsed_headers = {}
    for http_header in http_headers:
        i = http_header.index(b':')
        header_name = http_header[:i]
        header_value = http_header[i + 1:].strip()
        header_name = header_name.decode('ascii')
        header_value = header_value.decode('ascii')
        parsed_headers[header_name] = header_value

    return Request(
        method=method.decode('ascii'),
        path=path.decode('ascii'),
        proto=proto,
        headers=parsed_headers
    )


class Request:
    def __init__(self, **fields):
        self.__dict__.update(fields)
