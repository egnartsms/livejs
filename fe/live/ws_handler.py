import collections
import json
import re
import sublime
import threading

from live.common.misc import index_where
from live.common.misc import stopwatch
from live.coroutine import co_driver
from live.gstate import config


MAIN_CHANNEL = 'main'


class BackendError(Exception):
    def __init__(self, message, **attrs):
        self.message = message
        self.__dict__.update(attrs)

    @classmethod
    def make(cls, info):
        def camel_to_underscore(s):
            return re.sub(r'(?<![A-Z])[A-Z]', lambda m: '_' + m.group().lower(), s)

        return cls(**{camel_to_underscore(k): v for k, v in info.items()})


class GenericError(BackendError):
    name = 'generic'


class DuplicateKeyError(BackendError):
    name = 'duplicate_key'


class GetterThrewError(BackendError):
    name = 'getter_threw'


be_errors = {sub.name: sub for sub in BackendError.__subclasses__()}


def make_be_error(name, info):
    return be_errors[name].make(info)


class WsHandler:
    def __init__(self):
        self.messages = []
        self.is_requested_processing = False
        self.is_directly_processing = False
        self.cond_processing = threading.Condition()
        self.websocket = None
        self.cb_on_connected = None
        self.persist_handlers = None

    @property
    def is_connected(self):
        return self.websocket is not None

    # def on_connected(self):
    #     def wrapper(fn):
    #         assert self.cb_on_connected is None
    #         self.cb_on_connected = fn
    #         # This is only needed for re-loading the project in development.  The code
    #         # may register for on_connected callback after the browser has already re-
    #         # established connection.
    #         if self.is_connected:
    #             self._fire_connected()
    #         return fn
    #     return wrapper

    def _fire_connected(self):
        if not self.cb_on_connected:
            return
        sublime.set_timeout(self.cb_on_connected, 0)

    def connect(self, websocket):
        assert not self.is_connected
        
        self.websocket = websocket
        self._fire_connected()
        print("LiveJS: BE websocket connected")

    def disconnect(self):
        assert self.is_connected
        self.websocket = None

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

        for msg in messages:
            self._process_message(msg)

    def _process_message(self, msg):
        if msg['type'] == 'result':
            self._process_op_result(msg)
        elif msg['type'] == 'persist':
            self._process_persist(msg)
        else:
            raise RuntimeError("Got a message of unknown type: {}".format(msg))

    def _process_persist(self, msg):
        assert msg['type'] == 'persist'

        for desc in msg['descriptors']:
            self._process_persist_descriptor(desc)

    def _process_persist_descriptor(self, desc):
        handler = self.persist_handlers[desc['operation']]
        handler(desc)

    def _process_op_result(self, msg):
        assert msg['type'] == 'result'

        if co_driver.is_free(MAIN_CHANNEL):
            sublime.error_message("LiveJS: received unexpected BE response: {}"
                                  .format(msg))
            raise RuntimeError

        if msg['success']:
            co_driver.send_to(MAIN_CHANNEL, msg['value'])
        else:
            be_error = make_be_error(msg['error'], msg['info'])
            try:
                co_driver.throw_in(MAIN_CHANNEL, be_error)
            except BackendError:
                sublime.error_message("LiveJS failure:\n{}".format(be_error.message))

    def run_async_op(self, operation, args):
        self.websocket.enqueue_message(json.dumps({
            'operation': operation,
            'args': args
        }))

    def run_sync_op(self, operation, args, report_be_error=True):
        assert co_driver.is_free(MAIN_CHANNEL),\
            "Cannot run synchronous operation: another BE interaction is in progress"

        def result_arrived():
            return index_where(self.messages, lambda msg: msg['type'] == 'result')

        stopwatch.start('sync_request')
        self.run_async_op(operation, args)
        self.is_directly_processing = True

        try:
            with self.cond_processing:
                idx = self.cond_processing.wait_for(result_arrived,
                                                    timeout=config.max_gui_freeze)
                if idx is None:
                    sublime.status_message(
                        "Operation aborted, BE took too long to respond"
                    )
                    raise RuntimeError("BE synchronous communication timeout")

                head_messages = self.messages[:idx]
                result = self.messages[idx]
                del self.messages[:(idx + 1)]

                # If there are more, schedule a callback
                if self.messages:
                    self._schedule_message_processing()

            # First process head_messages which consists of persists only
            for msg in head_messages:
                self._process_persist(msg)
            
            # Done, return the result
            if result['success']:
                return result['value']
            else:
                be_error = make_be_error(result['error'], result['info'])
                if report_be_error:
                    sublime.error_message("LiveJS failure:\n{}".format(be_error.message))
                raise be_error
        finally:
            self.is_directly_processing = False


ws_handler = WsHandler()
