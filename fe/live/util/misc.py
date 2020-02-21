import time
import contextlib
import uuid


def file_contents(filepath):
    with open(filepath, 'r') as fl:
        return fl.read()


def gen_uid():
    return uuid.uuid4().hex


def eraise(msg=None, *args, **kwargs):
    if msg is None:
        raise RuntimeError
    else:
        raise RuntimeError(msg.format(*args, **kwargs))


def first_or_none(gen):
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


def index_where(iterable, pred=None):
    for i, x in enumerate(iterable):
        if pred and pred(x) or x:
            return i


def serially(*iterables):
    iterators = [iter(iterable) for iterable in iterables]
    while True:
        for iterator in iterators:
            yield next(iterator)


def take_over_list_items(lst):
    """Delete all elements from lst and return them in a new list.

    This is useful in a multithreading environment where multiple threads treat a list
    object as a queue, and use no locks. This function is designed to be called by the
    consumer to get a list of items he needs to process. It is important that after this
    function returns the original list object may be already non-empty if the producer has
    put something in it.  The consumer should be prepared for this and arrange his data
    structures accordingly.
    """
    copy = lst[:]
    del lst[:len(copy)]
    return copy


class Stopwatch:
    def __init__(self):
        self.moments = {}

    def start(self, name):
        self.moments[name] = time.perf_counter()

    def elapsed(self, name):
        return time.perf_counter() - self.moments[name]

    def print(self, name, msg):
        elapsed = self.elapsed(name)
        print(msg.format(name=name, elapsed=elapsed))

    def printstop(self, name):
        self.print(name, "stopwatch {name} finished in {elapsed}")
        del self.moments[name]


stopwatch = Stopwatch()


class Proxy:
    __slots__ = 'target',

    def __init__(self):
        object.__setattr__(self, 'target', None)

    def __getattribute__(self, name):
        return getattr(_get_proxy_target(self), name)

    def __setattr__(self, name, value):
        setattr(_get_proxy_target(self), name, value)

    def __delattr__(self, name):
        delattr(_get_proxy_target(self), name)

    def __call__(self, *args, **kwargs):
        return _get_proxy_target(self)(*args, **kwargs)


def set_proxy_target(proxy, target):
    object.__setattr__(proxy, 'target', target)


def _get_proxy_target(proxy):
    return object.__getattribute__(proxy, 'target')


missing = object()


@contextlib.contextmanager
def mapping_key_set(mapping, key, value):
    old_value = mapping[key] if key in mapping else missing
    mapping[key] = value
    try:
        yield
    finally:
        if old_value is missing:
            del mapping[key]
        else:
            mapping[key] = old_value


class FreeObj:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
