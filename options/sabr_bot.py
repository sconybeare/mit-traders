import ticker_lib
import copy
import monotonic as clock
import utils
import math

import sabr_lib
import vollib.black_scholes.implied_volatility as ivol

from generic_bot import Generic_Bot

import csv
import sys


class SABR_Bot(Generic_Bot):
    def __init__(self, limiter, scheduler):
        Generic_Bot.__init__(self, limiter, scheduler)
        self.pricer = SabrPricer()
        self.start_ts = None

    def onMarketUpdate(self, *args):
        Generic_Bot.onMarketUpdate(self, *args)
        pass

    def onAckRegister(self, *args):
        Generic_Bot.onAckRegister(self, *args)
        pass

    def onTraderUpdate(self, msg, order):
        Generic_Bot.onTraderUpdate(self, msg, order)
        print msg

    def maturity(self):
        return 450 - self.elapsed_time

    # estimates fair value as the middle of the bid-ask spread
    def mid(self, ticker):
        book = self.market_books[ticker]
        bid = book['sorted_bids'][0]
        bid_sz = book['bids'][bid]
        ask = book['sorted_asks'][0]
        ask_sz = book['asks'][ask]

        return (bid + ask) / 2

    def last(self, ticker):
        return self.market_books[ticker]['last_price']

    # Averages the at-the-money implied volatility for puts and calls, interpolating linearly between
    # the two nearest strikes
    def at_money_vol(self):
        fut_tckr = ticker_lib.futures
        spot = self.last(fut_tckr)
        K = int(round(spot))
        (self.market_implied_vol(K, 'P') + self.market_implied_vol(K, 'C')) / 2

    def market_implied_vol(self, K, option_dir):
        fut_tckr = ticker_lib.futures

        spot = self.last(fut_tckr)

        if not (80 <= K <= 120):
            raise ValueError

        K0 = int(math.floor(K))
        K1 = int(math.ceil(K))

        opt_ticker_0 = ticker_lib.option_tickers[(K0, option_dir)]
        opt_ticker_1 = ticker_lib.option_tickers[(K1, option_dir)]
        price = self.last(option_ticker)

        T = self.maturity()

        implied_vol_0 = ivol.implied_volatility(price, spot, K, T, 0.0, option_dir.lower())
        implied_vol_1 = ivol.implied_volatility(price, spot, K, T, 0.0, option_dir.lower())

        return (K1 - K)*implied_vol_0 + (K - K0)*implied_vol_1
