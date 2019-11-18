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
