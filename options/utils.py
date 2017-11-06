# Convenience functions, mostly to help interact with the mangocore api
import math
import collections
import monotonic as clock
import heapq
from datetime import datetime

def translate_book(order_book):
    return {float(k) : order_book[k] for k in order_book}

def convert_market_state(market_state):
    assert 'ticker' in market_state
    for side in ['bids', 'asks']:
        market_state[side] = translate_book(market_state[side])
        market_state['sorted_' + side] = sorted(market_state[side].keys(), reverse=(side == 'bids'))

def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")

class RateLimiter:
    def __init__(self, quota, period_seconds):
        self.quota = int(quota)
        self.period_seconds = float(period_seconds)
        self.restore_queue = collections.deque()

    def amount_available(self):
        ts = clock.monotonic()

        # Return expired borrows to the quota
        while self.restore_queue:
            restore_amount, borrow_ts = self.restore_queue[0]
            if ts - borrow_ts > self.period_seconds:
                self.quota += restore_amount
                self.restore_queue.popleft()
            else:
                break
        return self.quota

    # borrows n from quota if possible, returns boolean success
    # TODO restore from queue before checking for exception case
    def borrow(self, n):
        ts = clock.monotonic()
        if n > self.quota:
            raise BorrowError
        self.quota -= n
        self.restore_queue.append((n, ts))
        return

class BorrowError(Exception):
    pass

# Implementation of timer events
class Scheduler:
    def __init__(self):
        self.tasks = []
        self.__flush = False

    def flush(self):
        self.__flush = True

    def schedule_delay(self, f, delay):
        ts = clock.monotonic()
        self.schedule_absolute(f, ts + delay)

    def schedule_absolute(self, f, t_run):
        heapq.heappush(self.tasks, (t_run, f))

    def schedule_now(self, f):
        return self.schedule_absolute(f, clock.monotonic())

    # Attempts to get the next ready job, returns None if there's no ready job
    def __pop_job(self):
        if not self.tasks:
            return None
        t_run, f = self.tasks[0]
        time_remaining = t_run - clock.monotonic()
        if time_remaining > 0:
            return None
        heapq.heappop(self.tasks)
        return f

    def __run_next_job(self, order):
        f = self.__pop_job()
        if f is not None:
            f(order)
            return True
        else:
            return False

    def run(self, order):
        self.__run_next_job(order)


class OrderWrapper:
    def __init__(self, limiter):

        class WrappedOrder:

            def __init__(self, order):
                self.activated = False
                self.order = order
                self.reserved_capacity = 0

            def activate(self):
                if not self.activated:
                    self.borrow(1)
                    self.activated = True

            def reserve_active(self, n):
                if self.activated:
                    self.reserve(n+1)
                else:
                    self.reserve(n)

            def reserve(self, n):
                limiter.borrow(n)
                self.reserved_capacity += n

            def borrow(self, n):
                from_reservation = min(self.reserved_capacity, n)
                from_quota = n - from_reservation
                if from_quota == 0:
                    self.reserved_capacity -= from_reservation
                else:
                    limiter.borrow(from_quota)
                    self.reserved_capacity = 0

            def addBuy(self, *args, **kwargs):
                self.activate()
                self.borrow(1)
                self.order.addBuy(*args, **kwargs)

            def addSell(self, *args, **kwargs):
                self.activate()
                self.borrow(1)
                self.order.addSell(*args, **kwargs)

            def addTrade(self, *args, **kwargs):
                self.activate()
                self.borrow(1)
                self.order.addTrade(*args, **kwargs)

            def addCancel(self, *args, **kwargs):
                self.activate()
                self.borrow(1)
                self.order.addCancel(*args, **kwargs)


        self.wrap = WrappedOrder

    def dec(self, f):
        def g(msg, order):
            wrapped_order = self.wrap(order)
            return f(msg, wrapped_order)
        return g
