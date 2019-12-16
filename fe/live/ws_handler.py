import sublime

import json
import collections

from live.util import stopwatch
from live.code.action_handlers import action_handlers


class WsHandler:
    def __init__(self):
        self.callbacks = []
        self.responses = []
        self.requested_processing_on_main_thread = False
        self.websocket = None

    @property
    def is_connected(self):
        return self.websocket is not None

    def connect(self, websocket):
        if self.is_connected:
            raise RuntimeError("WsHandler attempted to connect while already connected")
        self.websocket = websocket
        print("LiveJS: BE websocket connected")

    def disconnect(self):
        if not self.is_connected:
            raise RuntimeError("WsHandler attempted to disconnect while not connected")
        self.websocket = None
        print("LiveJS: BE websocket disconnected")

    def __call__(self, data):
        """Called by the WS code as soon as a message arrives.

        This is called by the eventloop worker thread.

        :param data: str/bytes object sent via this connection
        """
        self.responses.append(data)
        if not self.requested_processing_on_main_thread:
            self.requested_processing_on_main_thread = True
            sublime.set_timeout(self._process_responses, 0)

    def _process_responses(self):
        self.requested_processing_on_main_thread = False

        while self.responses:
            if not self.callbacks:
                sublime.error_message("LiveJS: logic error: got more responses than "
                                      "expected")
                return

            callback = self.callbacks.pop(0)
            response = self.responses.pop(0)
            data = json.loads(response, object_pairs_hook=collections.OrderedDict)

            if not data['success']:
                sublime.error_message("LiveJS BE failed: {}".format(data['message']))
                continue

            self._perform_actions(data['actions'])

            if callback is not None:
                callback(response=data['response'])

    def _perform_actions(self, actions):
        """Handle the BE response on the main thread"""
        for action in actions:
            stopwatch.start('action_{}'.format(action['type']))
            handler = action_handlers[action['type']]
            handler(action)

    def request(self, msg, callback=None):
        if not self.is_connected:
            raise RuntimeError("WsHandler is not connected")
        
        self.callbacks.append(callback)
        self.websocket.enqueue_message(msg)


ws_handler = WsHandler()
