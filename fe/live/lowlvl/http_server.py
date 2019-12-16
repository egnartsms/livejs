"""Home-made asynchronous HTTP server.

It serves some static files and websocket requests. Websocket is where all the FE/BE
communication is done."""
import socket
import os
import http.client as httpcli


from live.lowlvl.eventloop import get_event_loop, Fd
from live.lowlvl.websocket import WebSocket
from live.gstate import config
from live.lowlvl.http import recv_up_to_delimiter, Request, Response


def serve(port, ws_handler):
    """Http server main coroutine.

    :param ws_handler: a WebSocket handler object. Required to have this interface:
        ws_handler.connect(websocket)
        ws_handler.disconnect()
        ws_handler.is_connected
        ws_handler(message)
    """
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
        if ws_handler.is_connected:
            yield from Response(req, httpcli.BAD_REQUEST).send_empty()
        else:
            websocket = WebSocket(req, ws_handler)
            ws_handler.connect(websocket)
            try:
                yield from websocket
            finally:
                ws_handler.disconnect()

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
