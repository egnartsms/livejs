"""Coroutines (generators) that are executed on main thread.

This is not related to the eventloop coroutines.
"""
import functools
import inspect


class CoDriver:
    def __init__(self):
        self.coroutines = set()
        self.co_running = None
        self.name_to_co = {}
        self.co_to_name = {}

    def is_free(self, name):
        return not self.is_occupied(name)

    def is_occupied(self, name):
        return name in self.name_to_co

    def forget_all(self):
        assert self.co_running is None
        self.coroutines.clear()
        self.name_to_co.clear()
        self.co_to_name.clear()

    def add_coroutine(self, co, name=None):
        assert co not in self.coroutines
        self.coroutines.add(co)
        if name is not None:
            assert name not in self.name_to_co
            self.name_to_co[name] = co
            self.co_to_name[co] = name
        self.send_to(co, None)

    def send_to(self, co_spec, value):
        self._advance(co_spec, lambda co: co.send(value))

    def throw_in(self, co_spec, exc):
        self._advance(co_spec, lambda co: co.throw(exc))

    def _advance(self, co_spec, action):
        co = self._getco(co_spec)
        try:
            self.co_running = co
            try:
                action(co)
            finally:
                self.co_running = None
        except StopIteration:
            self._forget(co)
        except Exception:
            self._forget(co)
            raise

    def _forget(self, co):
        self.coroutines.remove(co)
        name = self.co_to_name.get(co)
        if name is not None:
            del self.co_to_name[co]
            del self.name_to_co[name]

    def _getco(self, co_spec):
        return co_spec if inspect.isgenerator(co_spec) else self.name_to_co[co_spec]

    def callback(self, kind):
        assert self.co_running is not None

        co = self.co_running

        def _callback(arg=None):
            self.send_to(co, (kind, arg))

        return _callback


co_driver = CoDriver()


def coroutine():
    def wrapper(fn):
        assert inspect.isgeneratorfunction(fn)

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            gtor = fn(*args, **kwargs)
            co_driver.add_coroutine(gtor)

        return wrapped

    return wrapper
