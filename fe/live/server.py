"""Home-made asynchronous HTTP server"""
import socket
import os
import http.client as httpcli

from live.eventloop import get_event_loop, Fd
from live.websocket import WSConnection
from live.config import config
from live.http import recv_up_to_delimiter, Request, Response


websocket = None


def serve(port, ws_handler):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    sock.listen(5)

    try:
        while True:
            yield Fd.read(sock)
            cli, address = sock.accept()
            co = handle_http_request_wrapper(cli, ws_handler)
            co.send(None)
            get_event_loop().add_coroutine(co)
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request_wrapper(sock, ws_handler):
    """Make sure sock is properly closed"""
    try:
        yield None
        while (yield from handle_http_request(sock, ws_handler)):
            pass
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request(sock, ws_handler):
    """Handle 1 HTTP request.

    :return: True if another request should be handled through this connection
    """
    global websocket

    buf = bytearray()

    headers = yield from recv_up_to_delimiter(sock, buf, b'\r\n\r\n')
    if headers is None:
        return False

    req = Request.from_network(sock, headers)

    if req.path == '/wsconnect':
        if websocket is not None:
            yield from Response(req, httpcli.BAD_REQUEST).send_empty()
        else:
            websocket = WSConnection(req, ws_handler)
            try:
                yield from websocket
            finally:
                websocket = None

        return False

    moveon = req.headers.get('connection') == 'keep-alive'

    if req.path == '/':
        filename = 'page.html'
    else:
        filename = req.path[1:]

    filepath = os.path.join(config.be_root, filename)
    if not os.path.exists(filepath):
        yield from Response(req, httpcli.NOT_FOUND).send_empty()
        return moveon

    yield from Response(req, httpcli.OK).send_file(filepath)
    return moveon
