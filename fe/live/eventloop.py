"""Home-made eventloop (Python 3.3 does not yet have asyncio)"""
import select
from collections import namedtuple, deque
import threading
import weakref
import functools

from live.eventfd import EventFd
from live.blink import Blinker


FdRead = namedtuple('FdRead', 'fd')
FdWrite = namedtuple('FdWrite', 'fd')


class ThreadLocal(threading.local):
    def __getattr__(self, name):
        setattr(self, name, None)
        return None


tl_info = ThreadLocal()


def is_event_loop_running():
    return tl_info.event_loop is not None


def get_event_loop():
    assert tl_info.event_loop is not None
    return tl_info.event_loop


def is_fd(obj):
    return isinstance(obj, (FdRead, FdWrite))


def check_not_running_event_loop():
    if is_event_loop_running():
        raise RuntimeError("Already running an event loop in this thread")


class CoroutineState:
    __slots__ = ('is_finished', 'result')

    def __init__(self):
        self.is_finished = False
        self.result = None

    def finished_with(self, value_or_exc):
        self.is_finished = True
        self.result = value_or_exc


class EventLoop:
    def __init__(self):
        self.evt_interrupt = EventFd()
        self.service_actions = deque()
        self.active = []
        self.wblocked = []
        self.rblocked = []
        self.stop_when_empty = False
        self.run_by_thread = None
        # {iterator: CoroutineState}
        self.coroutines = weakref.WeakKeyDictionary()
        # {name: itr}, for human convenience, to hold onto coroutine by names.
        self.named_coroutines = {}
        # synchronizes changes to self.coroutines
        #self.lock_coroutines = threading.Lock()
        # fires when any coroutine finishes
        #self.cv_finished = threading.Condition(self.lock_coroutines)
        self.blink_co_finished = Blinker()
        # {itr: exc}: raise exc in itr on the next loop iteration
        self.to_raise = {}
        # intent to stop the event loop
        self.stop_flag = False
        # protects this event loop's running state (on/off)
        self.cv_running_state = threading.Condition(threading.Lock())
        # In case self.run() raised we store the exception
        self.raised = None
        self.exc_handler = None

    def run(self):
        check_not_running_event_loop()

        with self.cv_running_state:
            if self.is_running:
                self._eventloop_exception(
                    RuntimeError("Attempt to run event loop from multiple threads")
                )
            self.run_by_thread = threading.current_thread()
            tl_info.event_loop = self
            self.cv_running_state.notify_all()

        self.stop_flag = False
        self.raised = None

        try:
            self._run()
        except Exception as e:
            self._eventloop_exception(e)
        finally:
            self.stop_when_empty = False
            with self.cv_running_state:
                tl_info.event_loop = None
                self.run_by_thread = None
                self.cv_running_state.notify_all()

    def _run(self):
        while not self.stop_flag:
            while self.to_raise:
                itr, exc = self.to_raise.popitem()
                found = self._remove_coroutine_from_lists(itr)
                if found:
                    self._co_yielded(itr, self._co_throw(itr, exc))

                if self.stop_flag:
                    return

            while self.active:
                itr = self.active.pop(0)
                self._co_yielded(itr, self._co_send(itr))

                if self.stop_flag:
                    return

            if self.stop_when_empty and not self.rblocked and not self.wblocked:
                return

            wait_read = [fd for itr, fd in self.rblocked]
            wait_write = [fd for itr, fd in self.wblocked]

            ready_read, ready_write, ready_exc = select.select(
                wait_read + [self.evt_interrupt],
                wait_write,
                wait_read + wait_write
            )

            if ready_exc != []:
                raise RuntimeError("ready_exc is not empty: {}".format(ready_exc))

            self.active.extend(itr for itr, fd in self.rblocked if fd in ready_read)
            self.active.extend(itr for itr, fd in self.wblocked if fd in ready_write)
            self.rblocked = [(itr, fd) for itr, fd in self.rblocked
                             if fd not in ready_read]
            self.wblocked = [(itr, fd) for itr, fd in self.wblocked
                             if fd not in ready_write]

            self.evt_interrupt.clear()

    def _remove_coroutine_from_lists(self, itr):
        """Look for itr in active, rblocked and wblocked, and remove it.
        
        Return whether itr was found in any of these places.
        """
        if itr in self.active:
            self.active.remove(itr)
            return True

        idx = next((i for i, (x, fd) in enumerate(self.rblocked) if x is itr),
                   None)
        if idx is not None:
            self.rblocked.pop(idx)
            return True

        idx = next((i for i, (x, fd) in enumerate(self.wblocked) if x is itr),
                   None)
        if idx is not None:
            self.wblocked.pop(idx)
            return True

        return False

    def _co_yielded(self, itr, fd):
        if fd is None:
            pass
        elif isinstance(fd, FdRead):
            self.rblocked.append((itr, fd.fd))
        elif isinstance(fd, FdWrite):
            self.wblocked.append((itr, fd.fd))
        else:
            raise RuntimeError(
                "A coroutine {} yielded unexpected value: {}".format(itr, fd)
            )

    def _co_send(self, itr):
        try:
            return itr.send(None)
        except StopIteration as e:
            self._record_coroutine_result(itr, e.value)
        except Exception as e:
            self._record_coroutine_result(itr, e)

        return None

    def _co_throw(self, itr, exc):
        try:
            return itr.throw(exc)
        except StopIteration as e:
            self._record_coroutine_result(itr, e.value)
        except Exception as e:
            self._unhandled_coroutine_exception(itr, e)
            self._record_coroutine_result(itr, e)

        return None

    def _record_coroutine_result(self, itr, res):
        self.coroutines[itr].finished_with(res)
        self.blink_co_finished.blink()

    def _unhandled_coroutine_exception(self, itr, exc):
        if self.exc_handler is not None:
            self.exc_handler(itr, exc)

    def _eventloop_exception(self, exc):
        self.raised = exc
        if self.exc_handler is not None:
            self.exc_handler(None, exc)
        raise exc

    @property
    def is_running(self):
        return self.run_by_thread is not None

    def join(self):
        """Wait till the event loop is empty"""
        check_not_running_event_loop()

        with self.cv_running_state:
            if self.is_running:
                self.stop_when_empty = True
                self.evt_interrupt.set()
                self.cv_running_state.wait_for(lambda: not self.is_running)
            if self.raised:
                raise self.raised

    def stop(self):
        """Wait until stopped"""
        check_not_running_event_loop()

        with self.cv_running_state:
            if self.is_running:
                self.stop_flag = True
                self.evt_interrupt.set()
                self.cv_running_state.wait_for(lambda: not self.is_running)
            if self.raised:
                raise self.raised

    def add_coroutine(self, itr, name=None):
        self.coroutines[itr] = CoroutineState()
        if name is not None:
            self.named_coroutines[name] = itr

        # Note: self.active is not protected with a lock because we're doing atomic
        # operations here. In self._run(), we also process it atomically. So we manage to
        # dispense with locking.
        self.active.append(itr)
        # OK without taking cv_running_state lock
        if self.is_running:
            self.evt_interrupt.set()

    def raise_in_coroutine(self, itr_or_name, exc):
        itr, name = self._named_coroutine(itr_or_name)
        # Note: self.to_raise is not protected with a lock because we're doing atomic
        # operations here. In self._run(), we also process it atomically. So we manage to
        # dispense with locking.
        self.to_raise[itr] = exc
        if self.is_running:
            self.evt_interrupt.set()

    def _named_coroutine(self, itr_or_name):
        if isinstance(itr_or_name, str):
            return self.named_coroutines[itr_or_name], itr_or_name
        else:
            return itr_or_name, None

    def _coroutine_state(self, itr_or_name):
        if isinstance(itr_or_name, str):
            itr = self.named_coroutines.get(itr_or_name)
            if itr is None:
                return None
        else:
            itr = itr_or_name

        return self.coroutines.get(itr)

    def _coroutine_result(self, state):
        if isinstance(state.result, Exception):
            raise state.result
        else:
            return state.result

    def is_coroutine_finished(self, itr_or_name):
        state = self._coroutine_state(itr_or_name)
        return state and state.is_finished

    def is_coroutine_running(self, itr_or_name):
        state = self._coroutine_state(itr_or_name)
        return state and not state.is_finished

    def join_coroutine(self, itr_or_name):
        check_not_running_event_loop()

        itr, name = self._named_coroutine(itr_or_name)

        self.blink_co_finished.wait_for(lambda: self.coroutines[itr].is_finished)

        # Yes, coroutine names are not synchronized because caller threads share the same
        # namespace and therefore responsible for avoiding name collisions.
        if name is not None:
            del self.named_coroutines[name]

        return self._coroutine_result(self.coroutines[itr])

    def run_coroutine(self, itr):
        """Add coroutine to self and run the loop on the current thread

        The event loop must not be already running.  Return the result of the coroutine.

        :note: This is a helper method and it is not thread-safe.
        """
        check_not_running_event_loop()

        if self.is_running:
            raise RuntimeError("Event loop already running")

        self.add_coroutine(itr)
        self.stop_when_empty = True
        self.run()
        return self._coroutine_result(self.coroutines[itr])

    def run_in_new_thread(self):
        threading.Thread(target=self.run).start()
