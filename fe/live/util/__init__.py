def tuplify(obj):
    if isinstance(obj, tuple):
        return obj
    else:
        return tuple(obj)


class AssocError(Exception):
    def __init__(self, x, y):
        self.x = x
        self.y = y
        super().__init__("Assoc_12m: X obj {} already associated with Y {}".format(x, y))


class AssocOneToMany:
    """Helper container for usage with select() call in Eventloop.

    1-to-many relationship with limited functionality. We call the sides X and Y.
    """
    
    def __init__(self):
        self._x2ys = dict()
        self._y2x = dict()

    def set_new(self, x, ys):
        ys = tuple(ys)
        if not ys:
            return
        
        assert x not in self._x2ys
        self._x2ys[x] = ys
        for y in ys:
            assert y not in self._y2x
            self._y2x[y] = x

    def remove_by(self, y):
        x = self._y2x[y]
        del self._x2ys[x]
