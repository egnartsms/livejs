"""Websocket server/client implementation (not intended for reuse)"""

import struct
import http.client as httpcli
import hashlib
import base64
from collections import deque


from live.lowlvl.http import Response, recv_next, recv_next_as_buf, send_buffer
from live.lowlvl.eventloop import Fd
from live.lowlvl.eventfd import EventFd


class OpCode:
    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


MAGIC_STRING = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


class WebSocket:
    def __init__(self, req, ws_handler):
        self.req = req
        self.sock = req.sock
        self.ws_handler = ws_handler
        self.queue_write = deque()
        self.evt_write = EventFd()

    def __iter__(self):
        ok = yield from self.handshake()
        if not ok:
            return

        while True:
            yield Fd.read(self.sock), Fd.read(self.evt_write)
            if self.evt_write.is_set():
                while self.queue_write:
                    msg = self.queue_write.popleft()
                    yield from self.send_message(msg)
                self.evt_write.clear()
            else:
                msg = yield from self.read_message()
                if msg is None:
                    break

                try:
                    self.ws_handler(msg)
                except Exception as e:
                    print("Got exception when processing WS message:")
                    print(e)

    def handshake(self):
        headers = self.req.headers
        if (headers.get('connection') != 'Upgrade' or
                headers.get('upgrade') != 'websocket'):
            yield from Response(self.req, httpcli.BAD_REQUEST).send_empty()
            return False

        wskey = headers.get('sec-websocket-key')
        if wskey is None:
            yield from Response(self.req, httpcli.BAD_REQUEST).send_empty()
            return False

        wsver = headers.get('sec-websocket-version')
        if wsver != '13':
            resp = Response(self.req, httpcli.BAD_REQUEST)
            resp.add_header('Sec-WebSocket-Version', '13')
            yield from resp.send_empty()
            return False

        resp = Response(self.req, httpcli.SWITCHING_PROTOCOLS)
        resp.add_header('Upgrade', 'websocket')
        resp.add_header('Connection', 'Upgrade')
        resp.add_header('Sec-WebSocket-Accept', sec_websocket_accept(wskey))
        yield from resp.send_empty()
        return True

    def read_message(self):
        frame = yield from read_frame(self.sock)
        if frame.opcode == OpCode.PING:
            self.send_message(Frame(fin=True, opcode=OpCode.PONG, payload=frame.payload))
        elif frame.opcode == OpCode.PONG:
            pass
        elif frame.opcode == OpCode.CLOSE:
            return None
        else:
            if frame.fin:
                return maybe_str(frame.payload, frame.opcode)

            opcode = frame.opcode
            pieces = [frame.payload]

            while not frame.fin:
                frame = yield from read_frame(self.sock)
                pieces.append(maybe_str(frame.payload, opcode))

            if opcode == OpCode.BINARY:
                return b''.join(pieces)
            else:
                return ''.join(pieces)

    def send_message(self, msg):
        msg = msg.encode('utf8')
        pieces = [(OpCode.TEXT | 0x80).to_bytes(1, 'big')]
        
        if len(msg) < 126:
            pieces.append(len(msg).to_bytes(1, 'big'))
        elif len(msg) < (1 << 16):
            pieces.append((126).to_bytes(1, 'big'))
            pieces.append(len(msg).to_bytes(2, 'big'))
        else:
            pieces.append((127).to_bytes(1, 'big'))
            pieces.append(len(msg).to_bytes(8, 'big'))

        pieces.append(msg)
        total = b''.join(pieces)

        yield from send_buffer(self.sock, total)

    def enqueue_message(self, msg):
        assert isinstance(msg, str)
        self.queue_write.append(msg)
        self.evt_write.set()


def sec_websocket_accept(wskey):
    return base64.b64encode(hashlib.sha1(wskey.encode('ascii') + MAGIC_STRING).digest())


'''
+-+-+-+-+-------+-+-------------+-------------------------------+
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
|     Extended payload length continued, if payload len == 127  |
+ - - - - - - - - - - - - - - - +-------------------------------+
|                     Payload Data continued ...                |
+---------------------------------------------------------------+
'''


class Frame:
    __slots__ = ('fin', 'opcode', 'payload')

    def __init__(self, fin, opcode, payload):
        self.fin = fin
        self.opcode = opcode
        self.payload = payload


def maybe_str(payload, opcode):
    assert opcode in (OpCode.BINARY, OpCode.TEXT)
    if opcode == OpCode.BINARY:
        return payload
    else:
        return payload.decode('utf-8')


def read_frame(sock):
    buf = bytearray()
    b0, b1 = yield from recv_next(sock, buf, 2)
    fin = bool(b0 & 0x80)
    opcode = b0 & 0x0F
    mask = bool(b1 & 0x80)
    if not mask:
        raise RuntimeError("Client sent unmasked frame")
    payload_len = b1 & 0x7F
    if payload_len < 126:
        pass
    elif payload_len == 126:
        (payload_len,) = struct.unpack('>H', (yield from recv_next(sock, buf, 2)))
    else:
        (payload_len,) = struct.unpack('>Q', (yield from recv_next(sock, buf, 8)))

    mask_key = yield from recv_next(sock, buf, 4)
    payload = yield from recv_next_as_buf(sock, buf, payload_len)

    for i in range(len(payload)):
        payload[i] = payload[i] ^ mask_key[i % 4]

    return Frame(fin=fin, opcode=opcode, payload=payload)
