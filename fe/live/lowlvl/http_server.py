"""Home-made asynchronous HTTP server.

It serves some static files and websocket requests. Websocket is where all the FE/BE
communication is done."""
import socket

from .eventloop import Fd
from .eventloop import get_event_loop
from .http import Request
from .sockutil import SocketClosedPrematurely
from .sockutil import recv_up_to_delimiter


def serve(port, request_handler):
    """Http server coroutine.

    :param request_handler: generator that processes all the HTTP requests, including
        websockets. It is called from a per-client coroutine like this:

        yield from request_handler()

    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('localhost', port))
    sock.listen(5)

    try:
        while True:
            yield Fd.read(sock)
            cli, address = sock.accept()
            co = handle_http_request_wrapper(cli, request_handler)
            co.send(None)
            get_event_loop().add_coroutine(co)
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request_wrapper(sock, request_handler):
    """Make sure sock is properly closed"""
    try:
        yield None

        moveon = True
        while moveon:
            try:
                moveon = yield from handle_http_request(sock, request_handler)
            except SocketClosedPrematurely:
                moveon = False
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request(sock, request_handler):
    """Handle 1 HTTP request.

    :return: True if another request should be handled through this connection
    """
    buf = bytearray()

    headers = yield from recv_up_to_delimiter(sock, buf, b'\r\n\r\n')
    req = Request.from_network(sock, headers)

    yield from request_handler(req)
    
    return req.headers.get('connection') == 'keep-alive'
