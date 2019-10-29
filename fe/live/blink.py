import threading


class Blinker:
    def __init__(self):
        self._waiters = []

    def wait(self):
        lock = threading.Lock()
        lock.acquire()
        self._waiters.append(lock)
        lock.acquire()

    def wait_for(self, predicate):
        lock = None
        while not predicate():
            if lock is None:
                lock = threading.Lock()
                lock.acquire()
            self._waiters.append(lock)
            lock.acquire()

    def blink(self):
        waiters = self._waiters[:]
        del self._waiters[:len(waiters)]
        for lock in waiters:
            lock.release()
