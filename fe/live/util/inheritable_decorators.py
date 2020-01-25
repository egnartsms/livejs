from collections import OrderedDict


def c3_linearize(bases):
    chains = [list(base.__mro__) for base in bases]
    chains.append(list(bases))
    result = []

    while True:
        tailset = {cls for chain in chains for cls in chain[1:]}
        found = None
        for chain in chains:
            if chain and chain[0] not in tailset:
                found = chain
                break

        if found is None:
            if not any(chains):
                return result
            else:
                raise RuntimeError("Unlinearizable base classes given: {}".format(bases))

        cls = found[0]
        result.append(cls)
        for chain in chains:
            chain[:] = [x for x in chain if x is not cls]

    return result


class ClassWithInheritableDecorators(type):
    @classmethod
    def __prepare__(mcls, name, bases):
        return OrderedDict()

    def __new__(mcls, name, bases, ns):
        # Collect own decorators
        decorators = [(name, value)
                      for name, value in ns.items()
                      if isinstance(value, InheritableDecorator)]

        my_inheritable_decorators = {}
        for _, decorator in decorators:
            my_inheritable_decorators.setdefault(decorator.method_name, [])\
                .append(decorator.wrapper)

        # We don't need InheritableDecorator namespace members -- get rid of these
        for name, _ in decorators:
            del ns[name]

        ns['_inheritable_decorators'] = my_inheritable_decorators

        # Compute ultimate normalized decorators map
        def merge(from_map, to_map):
            for method_name, wrappers in from_map.items():
                to_map.setdefault(method_name, []).extend(wrappers)

        total_map = {}
        for cls in reversed(c3_linearize(bases or [object])):
            if hasattr(cls, '_inheritable_decorators'):
                merge(cls._inheritable_decorators, total_map)
        merge(my_inheritable_decorators, total_map)

        for method_name, wrappers in total_map.items():
            if method_name in ns:
                meth = ns[method_name]
                for wrapper in reversed(wrappers):
                    meth = wrapper(meth)
                ns[method_name] = meth

        return super().__new__(mcls, name, bases, ns)


class InheritableDecorator:
    def __init__(self, method_name, wrapper):
        self.method_name = method_name
        self.wrapper = wrapper


def decorator_for(method_name, fn=None):
    def decorator(fn):
        return InheritableDecorator(method_name, fn)

    return decorator if fn is None else decorator(fn)
