"""Home-made eventloop (Python 3.3 does not yet have asyncio)"""
import select
from collections import namedtuple
import threading
import weakref

from live.eventfd import EventFd


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


ignored_generatorexit = type('', (object,), {
    '__repr__': lambda self: '<ignored GeneratorExit>'
})()


class EventLoop:
    def __init__(self):
        self.evt_interrupt = EventFd()
        self.active = []
        self.wblocked = []
        self.rblocked = []
        self.run_by_thread = None
        # {iterator: CoroutineState}
        self.coroutines = weakref.WeakKeyDictionary()
        # {name: itr}, for human convenience, to hold onto coroutine by names.
        self.named_coroutines = {}
        # [itr]: force quit itr (with itr.close())
        self.to_close = []
        # intent to stop the event loop
        self.stop_cmd = False
        self.handler_coroutine = None
        self.handler_eventloop = None

        # notifies when the event loop's running state changes
        self.cv_state = threading.Condition()

    @property
    def is_running(self):
        return self.run_by_thread is not None

    def coroutine_exc_handler(self, exc_handler):
        assert self.handler_coroutine is None
        self.handler_coroutine = exc_handler

    def eventloop_msg_handler(self, msg_handler):
        assert self.handler_eventloop is None
        self.handler_eventloop = msg_handler

    def run(self, autostop_condition=None):
        check_not_running_event_loop()

        with self.cv_state:
            if self.is_running:
                msg = "Attempt to run event loop from multiple threads"
                self._handle_eventloop_message(msg)
                raise RuntimeError(msg)
            self.run_by_thread = threading.current_thread()
            tl_info.event_loop = self
            self.cv_state.notify_all()

        self.stop_cmd = False

        try:
            self._run(autostop_condition=autostop_condition)
        except Exception as e:
            self._handle_eventloop_message(str(e))
            raise
        finally:
            with self.cv_state:
                tl_info.event_loop = None
                self.run_by_thread = None
                self.cv_state.notify_all()

    def _run(self, autostop_condition=None):
        while not self.stop_cmd:
            while self.to_close:
                itr = self.to_close.pop(0)
                found = self._remove_coroutine_from_lists(itr)
                if found:
                    self._force_quit_coroutine(itr)

                if self.stop_cmd:
                    break

            if self.stop_cmd:
                break

            while self.active:
                itr = self.active.pop(0)
                self._co_next(itr)

                if self.stop_cmd:
                    break

            if self.stop_cmd:
                break

            if autostop_condition is not None and autostop_condition():
                break

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

        if self.stop_cmd == 'just-quit':
            return
        elif self.stop_cmd == 'stop-coroutines':
            for itr in list(self.coroutines):
                found = self._remove_coroutine_from_lists(itr)
                if found:
                    # FIXME: notify_all() for each coroutine. It's better to have it only
                    # once, and hold the lock for the duration of the whole operation
                    self._force_quit_coroutine(itr)

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

    def _co_next(self, itr, exc=None):
        """Precondition: itr must not be recorded in any of the lists"""
        try:
            fd = itr.send(None) if exc is None else itr.throw(exc)
        except StopIteration as e:
            self._record_coroutine_result(itr, e.value)
            return
        except Exception as e:
            self._handle_coroutine_exception(itr, e)
            self._record_coroutine_result(itr, e)
            return

        if isinstance(fd, FdRead):
            self.rblocked.append((itr, fd.fd))
        elif isinstance(fd, FdWrite):
            self.wblocked.append((itr, fd.fd))
        else:
            # This is a programmer's error: coroutines must only yield smth that we know
            # how to feed to select system call.  So report this situation and close the
            # coroutine (the iterator object)
            self._handle_eventloop_message(
                "Coroutine {} yielded illegal object".format(itr, fd)
            )
            self._force_quit_coroutine(itr)

    def _force_quit_coroutine(self, itr):
        try:
            ret = itr.close()
        except Exception as ret:
            # It ignored GeneratorExit
            self._handle_eventloop_message(
                "Failed to close coroutine {}: {}".format(itr, ret)
            )

        self._record_coroutine_result(itr, ret)

    def _record_coroutine_result(self, itr, res):
        with self.cv_state:
            self.coroutines[itr].finished_with(res)
            self.cv_state.notify_all()

    def _handle_coroutine_exception(self, itr, exc):
        if self.handler_coroutine is not None:
            self.handler_coroutine(itr, exc)

    def _handle_eventloop_message(self, msg):
        if self.handler_eventloop is not None:
            self.handler_eventloop(msg)

    def stop(self, force_quit_coroutines=False):
        check_not_running_event_loop()

        with self.cv_state:
            if not self.is_running:
                return

            if force_quit_coroutines:
                self.stop_cmd = 'stop-coroutines'
            else:
                self.stop_cmd = 'just-quit'

            self.evt_interrupt.set()
            self.cv_state.wait_for(lambda: not self.is_running)

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

    def _named_coroutine(self, itr_or_name):
        if isinstance(itr_or_name, str):
            return self.named_coroutines[itr_or_name], itr_or_name
        else:
            return itr_or_name, None

    def _coroutine_state(self, itr_or_name):
        """Return coroutine state or None if no such coroutine registered"""
        if isinstance(itr_or_name, str):
            itr = self.named_coroutines.get(itr_or_name)
            if itr is None:
                return None
        else:
            itr = itr_or_name

        return self.coroutines.get(itr)

    def _coroutine_result(self, itr):
        state = self.coroutines[itr]
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

    def force_quit_coroutine(self, itr_or_name):
        """Force given coroutine to quit and wait for completion"""
        check_not_running_event_loop()

        itr, name = self._named_coroutine(itr_or_name)

        with self.cv_state:
            if not self.is_running:
                raise RuntimeError("Event loop is not running")

            self.to_close.push(itr)
            self.evt_interrupt.set()
            self.cv_state.wait_for(
                lambda: not self.is_running or self.coroutines[itr].is_finished
            )

            if not self.is_running:
                raise RuntimeError("Event loop stopped before coroutine had finished")

        # Yes, coroutine names are not synchronized because caller threads share the same
        # namespace and therefore responsible for avoiding name collisions.
        if name is not None:
            del self.named_coroutines[name]

        return self._coroutine_result(itr)

    def force_quit_all_coroutines(self):
        """Force all currently running coroutines to quit and wait for completion"""
        check_not_running_event_loop()

        with self.cv_state:
            if not self.is_running:
                raise RuntimeError("Event loop is not running")

            now_coroutines = list(self.coroutines)
            self.to_close.extend(now_coroutines)
            self.evt_interrupt.set()
            self.cv_state.wait_for(
                lambda: (not self.is_running or
                         all(self.is_coroutine_finished(co) for co in now_coroutines))
            )

            if not self.is_running:
                raise RuntimeError("Event loop stopped before coroutine had finished")

        self.named_coroutines.clear()

    def run_coroutine(self, itr):
        """Add coroutine to self and run the loop on the current thread

        The event loop must not be already running.  Return the result of the coroutine.

        :note: This is a helper method and it is not thread-safe.
        """
        check_not_running_event_loop()

        if self.is_running:
            raise RuntimeError("Event loop already running")

        self.add_coroutine(itr)
        self.run(autostop_condition=lambda: self.is_coroutine_finished(itr))
        return self._coroutine_result(itr)

    def run_in_new_thread(self):
        threading.Thread(target=self.run).start()
