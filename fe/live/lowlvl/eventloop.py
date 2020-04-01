"""Home-made eventloop (Python 3.3 does not yet have asyncio)"""
import select
import threading

from live.lowlvl.eventfd import EventFd


class Fd:
    __slots__ = ('fd', 'rw')

    def __init__(self, fd, rw):
        self.fd = fd
        self.rw = rw

    @property
    def is_read(self):
        return self.rw is False

    @property
    def is_write(self):
        return self.rw is True

    @classmethod
    def read(cls, fd):
        return cls(fd, False)

    @classmethod
    def write(cls, fd):
        return cls(fd, True)


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


def check_not_running_event_loop():
    if is_event_loop_running():
        raise RuntimeError("Already running an event loop in this thread")


class Coroutine:
    def __init__(self, itr, parent=None):
        self.itr = itr
        self.result = None
        self.r_fds = []
        self.w_fds = []
        self.send_fd = None
        self.parent = parent

    def finished(self, value_or_exc):
        self.itr = None
        self.result = value_or_exc
        self.send_fd = None
        del self.r_fds[:]
        del self.w_fds[:]

    @property
    def is_live(self):
        return self.itr is not None

    @property
    def is_finished(self):
        return self.itr is None
    
    @property
    def is_ready(self):
        return not self.r_fds and not self.w_fds

    @property
    def is_running(self):
        return self.itr.gi_running

    def get_result(self):
        if not self.is_finished:
            raise RuntimeError("Cannot get result from an unfinished coroutine")

        if isinstance(self.result, Exception):
            raise self.result
        else:
            return self.result


class EventLoop:
    def __init__(self):
        self.evt_interrupt = EventFd()
        self.live = set()  # {co}
        self.co_running = None
        self.ready = set()  # {co}
        self.r_fds = {}  # {fd: co}
        self.w_fds = {}  # {fd: co}
        self.to_quit = []  # [co] to force quit
        self.run_by_thread = None
        # {name: co}, for human convenience, to hold onto coroutine by names.
        self.co_named = {}
        # intent to stop the event loop
        self.stop_cmd = False
        self.error_handler = None

        # protects adding new coroutine, live/finished status of existing coroutines, and
        # is_running state of the event loop. Notifies when any of these changes.
        self.cv_state = threading.Condition()

    @property
    def is_running(self):
        return self.run_by_thread is not None

    def register_error_handler(self, error_handler):
        assert self.error_handler is None
        self.error_handler = error_handler

    def run(self, autostop_condition=None):
        check_not_running_event_loop()

        with self.cv_state:
            if self.is_running:
                msg = "Attempt to run event loop from multiple threads"
                self._report_error(msg)
                raise RuntimeError(msg)
            self.run_by_thread = threading.current_thread()
            tl_info.event_loop = self
            self.cv_state.notify_all()

        self.stop_cmd = False

        try:
            self._run(autostop_condition=autostop_condition)
        except Exception as e:
            self._report_error("Exception in eventloop thread:", e)
            raise
        finally:
            with self.cv_state:
                tl_info.event_loop = None
                self.run_by_thread = None
                self.cv_state.notify_all()

    def _run(self, autostop_condition=None):
        while not self.stop_cmd:
            while self.to_quit:
                co = self.to_quit.pop()
                if co.is_live:
                    self.ready.discard(co)
                    self._forget_selectables_of(co)
                    self._force_quit_coroutine(co)

            while self.ready:
                co = self.ready.pop()
                self._co_next(co)

                if self.stop_cmd:
                    break

            if self.stop_cmd:
                break

            if autostop_condition and autostop_condition():
                self.stop_cmd = 'stop-coroutines-&-quit'
                break

            ready_read, ready_write, ready_exc = select.select(
                list(self.r_fds) + [self.evt_interrupt],
                list(self.w_fds),
                list(self.r_fds) + list(self.w_fds)
            )

            if ready_exc != []:
                raise RuntimeError("ready_exc is not empty: {}".format(ready_exc))

            try:
                ready_read.remove(self.evt_interrupt)
            except ValueError:
                pass

            for ready_list, x_fds in ((ready_read, self.r_fds),
                                      (ready_write, self.w_fds)):
                for fd in ready_list:
                    co = x_fds[fd]
                    # If a coroutine was waiting for multiple descriptors and more than 1
                    # of them became ready simultaneously, we may get duplicated "ready"
                    # coroutines
                    if co not in self.ready:
                        co.send_fd = fd
                        self.ready.add(co)

            for co in self.ready:
                self._forget_selectables_of(co)

            self.evt_interrupt.clear()

        if self.stop_cmd == 'quit':
            pass
        elif self.stop_cmd == 'stop-coroutines-&-quit':
            for co in list(self.live):
                self._force_quit_coroutine(co)
        else:
            raise RuntimeError("Invalid stop_cmd: {}".format(self.stop_cmd))

    def _co_next(self, co):
        assert co.is_ready
        
        self.co_running = co
        try:
            try:
                fds = co.itr.send(co.send_fd)
            finally:
                self.co_running = None
        except StopIteration as e:
            self._record_coroutine_result(co, e.value)
            return
        except Exception as e:
            self._report_error(
                "Coroutine {} raised unhandled exception:".format(co.itr),
                e
            )
            self._record_coroutine_result(co, e)
            return

        if not isinstance(fds, tuple):
            fds = (fds, )

        for fd in fds:
            if not isinstance(fd, Fd):
                self._report_error(
                    "Coroutine {} yielded illegal object: {}".format(co.itr, fd)
                )
                self._force_quit_coroutine(co)
                return
            if fd.fd in self.r_fds if fd.is_read else self.w_fds:
                self._report_error("Coroutine {} returned a duplicate fd object to "
                                   "select from: {}".format(co.itr, fd.fd))
                self._force_quit_coroutine(co)
                return
        
        for fd in fds:
            if fd.is_read:
                co.r_fds.append(fd.fd)
                self.r_fds[fd.fd] = co
            else:
                co.w_fds.append(fd.fd)
                self.w_fds[fd.fd] = co

    def _force_quit_coroutine(self, co):
        self.co_running = co
        try:
            try:
                res = co.itr.close()
            finally:
                self.co_running = None
        except Exception as res:
            # It ignored GeneratorExit
            self._handle_eventloop_message(
                "Failed to close coroutine {}: {}".format(co.itr, res)
            )

        self._record_coroutine_result(co, res)

    def _record_coroutine_result(self, co, res):
        with self.cv_state:
            self.live.remove(co)
            co.finished(res)
            self.cv_state.notify_all()

    def _forget_selectables_of(self, co):
        for fd in co.r_fds:
            del self.r_fds[fd]
        del co.r_fds[:]

        for fd in co.w_fds:
            del self.w_fds[fd]
        del co.w_fds[:]

    def _report_error(self, msg, exc=None):
        if self.error_handler is not None:
            self.error_handler(msg, exc)
        else:
            print(msg)

    def add_coroutine(self, itr, name=None):
        with self.cv_state:
            co = Coroutine(itr, self.co_running)
            self.live.add(co)
            self.ready.add(co)
            if name is not None:
                assert self.run_by_thread != threading.current_thread(),\
                    "Temp restriction: cannot create nested named coroutines"
                self.co_named[name] = co
            if self.is_running:
                self.evt_interrupt.set()

            return co

    def force_quit_coroutine(self, name):
        check_not_running_event_loop()

        co = self.co_named[name]
        with self.cv_state:
            if not self.is_running:
                raise RuntimeError("Event loop is not running")

            closure = self._live_descendants_of(co)
            self.to_quit = closure.copy()
            self.evt_interrupt.set()
            self.cv_state.wait_for(
                lambda: not self.is_running or all(co.is_finished for co in closure)
            )

            if not self.is_running:
                raise RuntimeError("Event loop stopped unexpectedly")

            del self.co_named[name]

    def _live_descendants_of(self, root):
        def is_descendant(co):
            while co is not None and co is not root:
                co = co.parent
            return co is root

        return [co for co in self.live if is_descendant(co)]

    def stop(self, force_quit_coroutines=True):
        self._stop_with_cmd('stop-coroutines-&-quit' if force_quit_coroutines else 'quit')

    def _stop_with_cmd(self, stop_cmd):
        check_not_running_event_loop()

        with self.cv_state:
            if not self.is_running:
                return

            self.stop_cmd = stop_cmd
            self.evt_interrupt.set()

            self.cv_state.wait_for(lambda: not self.is_running)

    def is_coroutine_live(self, name):
        if name not in self.co_named:
            return False

        return self.co_named[name].is_live

    def run_coroutine(self, itr):
        """Add coroutine to self and run the loop on the current thread

        The event loop must not be already running.  Return the result of the coroutine.

        :note: This is a helper method and it is not thread-safe.
        """
        check_not_running_event_loop()

        if self.is_running:
            raise RuntimeError("Event loop already running")

        co = self.add_coroutine(itr)
        self.run(autostop_condition=lambda: co.is_finished)
        return co.get_result()

    def run_in_new_thread(self):
        threading.Thread(target=self.run).start()
