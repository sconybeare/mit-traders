import ticker_lib
import copy
import monotonic as clock
import utils

import sabr_lib
import vollib.black_scholes.implied_volatility as ivol

from generic_bot import Generic_Bot

import csv
import sys

outfile = open(sys.argv[1], 'w')
csv_writer = csv.writer(outfile)
csv_writer.writerow(['maturity', ticker_lib.futures] + [ticker_lib.option_tickers[(k, 'C')] + '-vol' for k in ticker_lib.strikes])

class SABR_Bot(Generic_Bot):
    def __init__(self, limiter, scheduler):
        Generic_Bot.__init__(self, limiter, scheduler)

    def onMarketUpdate(self, *args):
        Generic_Bot.onMarketUpdate(self, *args)

    def onAckRegister(self, *args):
        Generic_Bot.onAckRegister(self, *args)
        if not self.ivols_loop:
            self.loop_implied_vols(1)

    def maturity(self):
        return 450 - self.elapsed_time

    # gives the size-weighted mid method for estimating fair value
    def mid(self, ticker):
        book = self.market_books[ticker]
        bid = book['sorted_bids'][0]
        bid_sz = book['bids'][bid]
        ask = book['sorted_asks'][0]
        ask_sz = book['asks'][ask]

        return (bid + ask) / 2

    def last(self, ticker):
        return self.market_books[ticker]['last_price']

    # gives the size-weighted mid method for estimating fair value
    def weighted_mid(self, ticker):
        try:
            book = self.market_books[ticker]
            bid = book['sorted_bids'][0]
            bid_sz = book['bids'][bid]
            ask = book['sorted_asks'][0]
            ask_sz = book['asks'][ask]
        except IndexError:
            return self.market_books[ticker]['last_price']

        return (bid*ask_sz + ask*bid_sz) / (ask_sz + bid_sz)

    def vols(self, option_dir):
        implied_vols = [self.vol(k, option_dir)[1] for k in ticker_lib.strikes]
        fut_last = self.last(ticker_lib.futures)
        return fut_last, implied_vols

    def at_money_vol(self, option_dir):
        fut_tckr = ticker_lib.futures
        spot = self.last(fut_tckr)
        K = int(round(spot))
        return self.vol(K, option_dir)

    def vol(self, K, option_dir):
        fut_tckr = ticker_lib.futures

        spot = self.last(fut_tckr)

        if not 80 <= K <= 120:
            raise ValueError

        d = 'C'
        option_ticker = ticker_lib.option_tickers[(K, d)]
        price = self.last(option_ticker)

        T = self.maturity()

        implied_vol = ivol.implied_volatility(price, spot, K, T, 0.0, d.lower())

        return (K, implied_vol)
