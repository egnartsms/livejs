import functools

from live.common.misc import FreeObj


class AroundMethod:
    def __init__(self, fn):
        self.fn = fn

    def bind(self, instance, owner):
        return self.fn.__get__(instance, owner)


class PrimaryMethod:
    def __init__(self, fn):
        self.fn = fn

    def bind(self, instance, owner):
        return self.fn.__get__(instance, owner)

    @property
    def name(self):
        return self.fn.__name__

    def __get__(self, instance, owner):
        return wrap_primary_method(self, instance, owner)


def wrap_primary_method(primary, instance, owner):
    arounds = []

    for cls in reversed(owner.__mro__):
        meth = cls.__dict__.get(primary.name)
        if meth is primary:
            break
        if isinstance(meth, AroundMethod):
            arounds.append(meth.bind(instance, owner))
    else:
        raise RuntimeError("Method combination misuse")

    result = primary.bind(instance, owner)
    for around in reversed(arounds):
        result = wrap_around(around, result)

    return result


def wrap_around(around, nested):
    @functools.wraps(nested)
    def wrapped(*args, **kwargs):
        g = around(*args, **kwargs)
        res = None
        g_next = g.send

        while True:
            try:
                pass_args = g_next(res)
            except StopIteration as stop:
                return stop.value

            if pass_args is None:
                nested_args, nested_kwargs = args, kwargs
            else:
                nested_args, nested_kwargs = pass_args.args, pass_args.kwargs

            try:
                res = nested(*nested_args, **nested_kwargs)
            except Exception as e:
                res = e
                g_next = g.throw
            else:
                g_next = g.send

    return wrapped


class call_next:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


# Export interface
method = FreeObj(
    around=AroundMethod,
    primary=PrimaryMethod
)
