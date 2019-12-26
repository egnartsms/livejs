class Module:
    __slots__ = ('name', 'path')

    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)
