import sublime

import collections
import json
import threading

from live.code.persist_handlers import persist_handlers
from live.comm import BackendError
from live.comm import make_be_error
from live.gstate import config
from live.projects.operations import assign_window_for_livejs_project
from live.util.misc import index_where
from live.util.misc import stopwatch


class WsHandler:
    def __init__(self):
        self.messages = []
        # a generator yielding at points where it expects for BE to respond.
        self.cont = None
        self.is_requested_processing = False
        self.is_directly_processing = False
        self.cond_processing = threading.Condition()
        self.websocket = None

    @property
    def is_connected(self):
        return self.websocket is not None

    def connect(self, websocket):
        assert not self.is_connected
        
        self.websocket = websocket
        assign_window_for_livejs_project()
        print("LiveJS: BE websocket connected")

    def disconnect(self):
        assert self.is_connected
        self.websocket = None
        self.cont = None
        print("LiveJS: BE websocket disconnected")

    def __call__(self, data):
        """Called by the WS code as soon as a message arrives.

        This is called by the eventloop worker thread.

        :param data: str/bytes object sent via this connection
        """
        message = json.loads(data, object_pairs_hook=collections.OrderedDict)

        with self.cond_processing:
            self.messages.append(message)

            if self.is_directly_processing:
                self.cond_processing.notify_all()
            else:
                self._schedule_message_processing()

    def _schedule_message_processing(self):
        if not self.is_requested_processing:
            sublime.set_timeout(self._process_messages, 0)
            self.is_requested_processing = True

    def _process_messages(self):
        with self.cond_processing:
            messages = self.messages[:]
            del self.messages[:]
            self.is_requested_processing = False

        for message in messages:
            if message['type'] == 'response':
                self._process_response(message)
            elif message['type'] == 'persist':
                for req in message['requests']:
                    self._process_persist_request(req)
            else:
                assert 0, "Got a message of unknown type: {}".format(message)

    def _process_response(self, response):
        if self.cont is None:
            sublime.error_message("LiveJS: received unexpected BE response: {}"
                                  .format(response))
            raise RuntimeError

        feed = response_to_continuation_feed(response)
        self._cont_feed(feed)

    def _process_persist_request(self, req):
        stopwatch.start('action_{}'.format(req['type']))
        handler = persist_handlers[req['type']]
        handler(req)

    def _cont_feed(self, value):
        if isinstance(value, BackendError):
            self._cont_throw(value)
        else:
            self._cont_send(value)

    def _cont_send(self, value):
        try:
            reqtype, reqargs = self.cont.send(value)
        except StopIteration:
            self.cont = None
        except Exception:
            self.cont = None
            raise
        else:
            self._request(reqtype, reqargs)

    def _cont_throw(self, be_error):
        try:
            reqtype, reqargs = self.cont.throw(be_error)
        except StopIteration:
            self.cont = None
        except BackendError:
            self.cont = None
            sublime.error_message("LiveJS failure:\n{}".format(be_error.message))
        except Exception:
            self.cont = None
            raise
        else:
            self._request(reqtype, reqargs)

    def _request(self, reqtype, reqargs):
        self.websocket.enqueue_message(json.dumps({
            'type': reqtype,
            'args': reqargs
        }))

    def install_cont(self, cont):
        """Install the new continuation generator"""
        assert self.cont is None, "Cannot install a continuation (already installed)"

        self.cont = cont
        self._cont_send(None)

    def sync_request(self, reqtype, reqargs):
        assert self.cont is None,\
            "Cannot send blocking request: another BE interaction is in progress"

        def response_arrived():
            return index_where(self.messages, lambda msg: msg['type'] == 'response')

        stopwatch.start('sync_request')
        
        self._request(reqtype, reqargs)

        self.is_directly_processing = True

        try:
            with self.cond_processing:
                idx = self.cond_processing.wait_for(response_arrived,
                                                    timeout=config.max_gui_freeze)
                if idx is None:
                    sublime.status_message(
                        "Operation aborted, BE took too long to respond"
                    )
                    raise RuntimeError("BE synchronous communication timeout")

                head_messages = self.messages[:idx]
                response = self.messages[idx]
                del self.messages[:(idx + 1)]

                # If there are more, schedule a callback
                if self.messages:
                    self._schedule_message_processing()

            # First process head_messages which do not contain any responses
            for message in head_messages:
                assert message['type'] == 'persist'
                for req in message['requests']:
                    self._process_persist_request(req)
            
            # Done, return the response
            feed = response_to_continuation_feed(response)
            if isinstance(feed, BackendError):
                sublime.error_message("LiveJS failure:\n{}".format(feed.message))
                raise feed
            else:
                return feed
        finally:
            self.is_directly_processing = False


def response_to_continuation_feed(response):
    """Return either response value or an instance of BackendError (on failure)"""
    if response['success']:
        return response['value']
    else:
        return make_be_error(response['error'], response['info'])


ws_handler = WsHandler()
