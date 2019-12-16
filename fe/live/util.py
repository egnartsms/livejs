import time


def first_such(gen):
    return next(gen, None)


def tracking_last(iterable):
    i = iter(iterable)
    e0 = next(i)

    while True:
        try:
            e1 = next(i)
        except StopIteration:
            yield e0, True
            raise

        yield e0, False
        e0 = e1


def index_where(iterable):
    for i, x in enumerate(iterable):
        if x:
            return i


def serially(*iterables):
    iterators = [iter(iterable) for iterable in iterables]
    while True:
        for iterator in iterators:
            yield next(iterator)


class Stopwatch:
    def __init__(self):
        self.moments = {}

    def start(self, name):
        self.moments[name] = time.perf_counter()

    def print(self, name, msg):
        elapsed = time.perf_counter() - self.moments[name]
        print(msg.format(name=name, elapsed=elapsed))

    def printstop(self, name):
        self.print(name, "stopwatch {name} finished in {elapsed}")
        del self.moments[name]


stopwatch = Stopwatch()


class Proxy:
    __slots__ = 'target_getter',

    def __init__(self, target_getter):
        object.__setattr__(self, 'target_getter', target_getter)

    def __getattribute__(self, name):
        return getattr(_get_proxy_target(self), name)

    def __setattr__(self, name, value):
        setattr(_get_proxy_target(self), name, value)

    def __delattr__(self, name):
        delattr(_get_proxy_target(self), name)

    def __call__(self, *args, **kwargs):
        return _get_proxy_target(self)(*args, **kwargs)


def _get_proxy_target(proxy):
    return object.__getattribute__(proxy, 'target_getter')()
