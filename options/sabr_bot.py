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
        self.sabr_pricer = sabr_lib.SabrPricer()
        self.have_sabr_prices = False

    def onMarketUpdate(self, msg, order):
        Generic_Bot.onMarketUpdate(self, msg, order)

        market_state = msg['market_state']
        ticker = market_state['ticker']

        try:
            K, flag = ticker_lib.rev_option_tickers[ticker]
        except KeyError:
            return

        try:
            atm_vol = self.at_money_vol()
        except KeyError:
            print 'No spot price yet:'
            print sys.exc_info()
            return

        self.sabr_pricer.add_option_price(
            atm_vol, self.last(ticker_lib.futures),
            K, self.maturity(), 1 * (flag == 'c'), # This prevents numpy from casting everything to strings
            self.last(ticker), 1.0)

    def onAckRegister(self, *args):
        Generic_Bot.onAckRegister(self, *args)
        def f(order):
            print 'fitting rho and nu...'
            t0 = clock.monotonic()
            self.sabr_pricer.refit_model()
            self.have_sabr_prices = True
            t1 = clock.monotonic()
            print 'finished fitting rho and nu in', t1 - t0, 'seconds'
        # self.scheduler.schedule_delay(f, 30)

    def onTraderUpdate(self, msg, order):
        Generic_Bot.onTraderUpdate(self, msg, order)

    def onTrade(self, msg, order):
        Generic_Bot.onTraderUpdate(self, msg, order)

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
        return self.updated_books[ticker][u'last_price']

    # Averages the at-the-money implied volatility for puts and calls, interpolating linearly between
    # the two nearest strikes
    def at_money_vol(self):
        fut_tckr = ticker_lib.futures
        spot = self.last(fut_tckr)
        return (self.market_implied_vol(spot, 'p') + self.market_implied_vol(spot, 'c')) / 2

    def market_implied_vol(self, K, option_dir):
        fut_tckr = ticker_lib.futures

        spot = self.last(fut_tckr)

        if not (80 <= K <= 120):
            raise ValueError

        K0 = int(math.floor(K))
        K1 = int(math.ceil(K))

        opt_ticker_0 = ticker_lib.option_tickers[(K0, option_dir)]
        opt_ticker_1 = ticker_lib.option_tickers[(K1, option_dir)]
        price0 = self.last(opt_ticker_0)
        price1 = self.last(opt_ticker_1)

        T = self.maturity()

        implied_vol_0 = ivol.implied_volatility(price0, spot, K, T, 0.0, option_dir.lower())
        implied_vol_1 = ivol.implied_volatility(price1, spot, K, T, 0.0, option_dir.lower())

        return (K1 - K)*implied_vol_0 + (K - K0)*implied_vol_1

