import pytest
import re
import threading
import socket

from live.eventloop import EventLoop
from tests.async_server_client import (
    serve,
    connect,
    recv_1_response,
    recv_n_responses,
    StopServer,
    send_message
)


@pytest.fixture(scope='module')
def server():
    def kebab_to_camel(word):
        return re.sub('-([a-z])', lambda mo: mo.group(1).upper(), word)

    evt_up = threading.Event()
    eventloop = EventLoop(stop_when_empty=True)
    co_server = serve(8001, kebab_to_camel, evt_up)
    eventloop.add_coroutine(co_server)
    thread = threading.Thread(target=eventloop.run)
    thread.start()

    evt_up.wait()

    try:
        yield
    finally:
        eventloop.raise_in_coroutine(co_server, StopServer)
        eventloop.join_coroutine(co_server)
        thread.join()
        assert not thread.is_alive()


@pytest.mark.usefixtures('server')
def test_server_client_write_read():
    def client_coroutine():
        sock = yield from connect(8001)
        yield from send_message(sock, 'test-async-server-client')
        resp = yield from recv_1_response(sock)
        assert resp == 'testAsyncServerClient'
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()

    eventloop = EventLoop(stop_when_empty=True)
    eventloop.run_coroutine(client_coroutine())


@pytest.mark.usefixtures('server')
def test_server_client_write_multiple_read_multiple():
    def client_coroutine():
        sock = yield from connect(8001)
        N = 1000
        for i in range(N):
            yield from send_message(sock,
                                    'test-server-client-write-multiple-read-multiple')

        resps = yield from recv_n_responses(sock, N)
        for resp in resps:
            assert resp == 'testServerClientWriteMultipleReadMultiple'

        sock.shutdown(socket.SHUT_RDWR)
        sock.close()

    eventloop = EventLoop(stop_when_empty=True)
    eventloop.run_coroutine(client_coroutine())
