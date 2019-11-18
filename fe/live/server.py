"""Home-made asynchronous HTTP server"""
import socket
import os
import http.client as httpcli
import json
import collections

import sublime

from live.eventloop import get_event_loop, Fd
from live.websocket import WSConnection
from live.config import config
from live.http import recv_up_to_delimiter, Request, Response


websocket = None


def serve(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    sock.listen(5)

    try:
        while True:
            yield Fd.read(sock)
            cli, address = sock.accept()
            co = handle_http_request_wrapper(cli)
            co.send(None)
            get_event_loop().add_coroutine(co)
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request_wrapper(sock):
    """Make sure sock is properly closed"""
    try:
        yield None
        while (yield from handle_http_request(sock)):
            pass
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


def handle_http_request(sock):
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
            websocket = WSConnection(req, websocket_handler)
            print("WS connected")
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


response_callbacks = []

action_handlers = {}


def websocket_handler(ws, data):
    def handle_response():
        for action in data['actions']:
            assert action['type'] in action_handlers
            action_handlers[action['type']](action)

        if cb is not None:
            cb(response=data['response'])

    if not response_callbacks:
        sublime.error_message("LiveJS: logic error: expected response_callbacks not to "
                              "be empty")
        return

    cb = response_callbacks.pop(0)
    
    data = json.loads(data, object_pairs_hook=collections.OrderedDict)
    if not data['success']:
        sublime.error_message("LiveJS BE failed: {}".format(data['message']))
        return
    
    sublime.set_timeout(handle_response, 0)
