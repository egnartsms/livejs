if __name__ == '__main__':
    from weakref import WeakKeyDictionary

    class Hey:
        pass

    wd = WeakKeyDictionary()
    x = Hey()
    wd[x] = [x]
    del x
    print(len(wd))
    wd[list(wd)[0]][0] = 25
    print(len(wd))
