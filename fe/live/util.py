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
