"""Home-made eventloop (Python 3.3 does not yet have asyncio)"""
import select
from collections import namedtuple
import threading
import weakref

from live.eventfd import EventFd
from live.util import attr_set


FdRead = namedtuple('FdRead', 'fd')
FdWrite = namedtuple('FdWrite', 'fd')


class ThreadLocal(threading.local):
    def __getattr__(self, name):
        try:
            return threading.local.__getattr__(self, name)
        except AttributeError:
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


class EventLoop:
    def __init__(self, stop_when_empty=False):
        self.evt_interrupt = EventFd()
        self.service_actions = []
        self.active = []
        self.wblocked = []
        self.rblocked = []
        self.stop_when_empty = stop_when_empty
        self.is_running = False
        # {iterator: <ret value> OR <exc>}
        self.finished_coroutines = weakref.WeakKeyDictionary()
        self.raise_these = []
        # {iterator: <threading.Event object>}
        # Once the coroutine (iterator) is done, we should signal the specified Event
        # to unblock all threads waiting for it.
        self.cv_finished_coroutines = threading.Condition()

    def run(self):
        if is_event_loop_running():
            raise RuntimeError("Already running an event loop in this thread")
        if self.is_running:
            raise RuntimeError("Attempt to run the same event loop from multiple threads")

        tl_info.event_loop = self
        self.is_running = True

        try:
            self._run()
        finally:
            self.is_running = False
            tl_info.event_loop = None

    def _run(self):
        while True:
            self._raise_in_coroutines()

            for itr in self.active:
                fd = self._co_next(itr)

                if fd is None:
                    continue
                elif isinstance(fd, FdRead):
                    self.rblocked.append((itr, fd.fd))
                elif isinstance(fd, FdWrite):
                    self.wblocked.append((itr, fd.fd))
                else:
                    raise RuntimeError(
                        "A coroutine yielded unexpected value: {}".format(fd)
                    )

            del self.active[:]

            if self.stop_when_empty and not self.rblocked and not self.wblocked:
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
            for action in self.service_actions:
                action()
            del self.service_actions[:]

    def _raise_in_coroutines(self):
        for itr, exc in self.raise_these:
            if itr in self.active:
                self.active.remove(itr)
                self._co_throw(itr, exc)
                continue

            r_idx = next((i for i, (x, fd) in enumerate(self.rblocked) if x is itr),
                         None)
            if r_idx is not None:
                self.rblocked.pop(r_idx)
                self._co_throw(itr, exc)
                continue

            w_idx = next((i for i, (x, fd) in enumerate(self.wblocked) if x is itr),
                         None)
            if w_idx is not None:
                self.wblocked.pop(w_idx)
                self._co_throw(itr, exc)
                continue

            raise RuntimeError(
                "Cannot raise exc {} in coroutine {}: unknown coroutine".format(exc, itr)
            )

        del self.raise_these[:]

    def _co_next(self, itr):
        try:
            return next(itr)
        except StopIteration as e:
            self._record_coroutine_result(itr, e.value)
        except Exception as e:
            self._record_coroutine_result(itr, e)

        return None

    def _co_throw(self, itr, exc):
        try:
            itr.throw(exc)
        except StopIteration as e:
            self._record_coroutine_result(itr, e.value)
        except Exception as e:
            self._record_coroutine_result(itr, e)

    def _record_coroutine_result(self, itr, res):
        with self.cv_finished_coroutines:
            self.finished_coroutines[itr] = res
            self.cv_finished_coroutines.notify_all()

    def is_coroutine_running(self, itr):
        return (
            itr in self.active or
            any(x is itr for x, fd in self.rblocked) or
            any(x is itr for x, fd in self.wblocked)
        )

    def add_coroutine(self, itr):
        if self.is_coroutine_running(itr):
            raise RuntimeError("Coroutine {} is already running".format(itr))

        self._perform_service_action(lambda: self.active.append(itr))

    def raise_in_coroutine(self, itr, exc):
        if not self.is_coroutine_running(itr):
            raise RuntimeError("Coroutine {} is not found".format(itr))

        self._perform_service_action(lambda: self.raise_these.append((itr, exc)))

    def _perform_service_action(self, action):
        if self.is_running:
            self.service_actions.append(action)
            self.evt_interrupt.set()
        else:
            action()

    def get_coroutine_result(self, itr):
        result = self.finished_coroutines[itr]
        if isinstance(result, Exception):
            raise result
        else:
            return result

    def join_coroutine(self, itr, timeout=None):
        if is_event_loop_running():
            raise RuntimeError(
                "Cannot join coroutine from a thread that also runs an event loop"
            )

        with self.cv_finished_coroutines:
            self.cv_finished_coroutines.wait_for(lambda: itr in self.finished_coroutines,
                                                 timeout=timeout)

        return self.get_coroutine_result(itr)

    def run_coroutine(self, itr):
        if is_event_loop_running() or self.is_running:
            raise RuntimeError("Threading logical error")
        if not self.stop_when_empty:
            raise RuntimeError("The stop_when_empty must be set")

        self.stop_when_empty = True
        self.add_coroutine(itr)
        self.run()
        return self.join_coroutine(itr)
