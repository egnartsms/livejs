import sublime

import json
import collections
import traceback

from live.util import stopwatch, take_over_list_items, eraise
from live.code.persist_handlers import persist_handlers
from live.modules.operations import synch_modules_with_be


class WsHandler:
    def __init__(self):
        self.messages = []
        # a generator yielding at points where it expects for BE to respond
        self.cont = None
        self.requested_processing_on_main_thread = False
        self.websocket = None

    @property
    def is_connected(self):
        return self.websocket is not None

    def connect(self, websocket):
        if self.is_connected:
            eraise("WsHandler attempted to connect while already connected")
        self.websocket = websocket
        print("LiveJS: BE websocket connected")
        sublime.set_timeout(synch_modules_with_be, 0)

    def disconnect(self):
        if not self.is_connected:
            eraise("WsHandler attempted to disconnect while not connected")
        self.websocket = None
        self.cont = None
        print("LiveJS: BE websocket disconnected")

    def __call__(self, data):
        """Called by the WS code as soon as a message arrives.

        This is called by the eventloop worker thread.

        :param data: str/bytes object sent via this connection
        """
        message = json.loads(data, object_pairs_hook=collections.OrderedDict)
        self.messages.append(message)
        if not self.requested_processing_on_main_thread:
            self.requested_processing_on_main_thread = True
            sublime.set_timeout(self._process_messages_wrapper, 0)

    def _process_messages_wrapper(self):
        try:
            self._process_messages()
        except:
            traceback.print_exc()

    def _process_messages(self):
        self.requested_processing_on_main_thread = False

        for message in take_over_list_items(self.messages):
            if message['type'] == 'response':
                self._process_response(message)
            elif message['type'] == 'persist':
                for req in message['requests']:
                    self._process_persist_request(req)
            else:
                eraise("LiveJS: Got a message of unknown type: {}", message)

    def _process_response(self, response):
        if not response['success']:
            sublime.error_message("LiveJS request failed: {}".format(response['message']))

        if self.cont is None:
            eraise("LiveJS: received unexpected BE response: {}", response)

        if response['success']:
            try:
                reqtype, reqargs = self.cont.send(response['value'])
            except StopIteration:
                self.cont = None
            except:
                traceback.print_exc()
            else:
                self._request(reqtype, reqargs)
        else:
            self.cont = None

    def _process_persist_request(self, req):
        stopwatch.start('action_{}'.format(req['type']))
        handler = persist_handlers[req['type']]
        handler(req)

    def _request(self, reqtype, reqargs):
        self.websocket.enqueue_message(json.dumps({
            'type': reqtype,
            'args': reqargs
        }))

    def install_cont(self, cont):
        """Install the new continuation generator"""
        if self.cont is not None:
            eraise("Cannot install a continuation (already installed)")

        try:
            reqtype, reqargs = cont.send(None)
        except StopIteration:
            return

        self.cont = cont
        self._request(reqtype, reqargs)


ws_handler = WsHandler()
