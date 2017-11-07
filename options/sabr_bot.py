import ticker_lib
import copy
import monotonic as clock
import utils
import math
import numpy as np

import sabr_lib
import vollib.black_scholes.implied_volatility as ivol

from generic_bot import Generic_Bot

import csv
import sys

import random

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

class SABR_Bot(Generic_Bot):
    def __init__(self, limiter, scheduler):
        Generic_Bot.__init__(self, limiter, scheduler)
        self.sabr_pricer = sabr_lib.SabrPricer()
        self.have_sabr_prices = False

        self.order_size_mult = 10.0

        self.atm_vol = 0.008

        self.current_sabr_delta = 0.0
        self.current_sabr_vega = 0.0
        self.current_sabr_gamma = 0.0

        self.sabr_delta_fade = 0.000001
        self.sabr_vega_fade = 0.000035
        self.sabr_gamma_fade = 0.0001

        self.num_options_fade = 0.00001

        # TODO compute these and avoid fines
        self.current_black_delta = 0.0 # The black_delta limit is actually 200
        self.current_black_vega = 0.0 # Haven't actually found the black_vega limit
        self.current_black_gamma = 0.0
        self.current_num_options = 0

        self.min_taking_edge = 0.2

        self.token_prefix = ':SABRBOT:'

        self.delta_hedge_cutoff = 20.0

    def update_limited_positions(self):
        delta = 0.0
        vega = 0.0
        gamma = 0.0
        num_options = 0
        S = self.last(ticker_lib.futures)
        T = self.maturity()
        for ticker in self.positions:
            pos_amt = self.positions[ticker]
            if ticker == ticker_lib.futures:
                delta += pos_amt
            else:
                K, flag = ticker_lib.rev_option_tickers[ticker]
                price = self.last(ticker)
                delta += self.sabr_pricer.black_delta(price, S, K, T, flag)*pos_amt
                vega += self.sabr_pricer.black_vega(price, S, K, T, flag)*pos_amt
                gamma += self.sabr_pricer.black_gamma(price, S, K, T, flag)*pos_amt
                num_options += abs(pos_amt)
        self.current_black_delta = delta
        self.current_black_vega = vega
        self.current_black_gamma = gamma
        self.current_num_options = num_options

        print 'black_delta =', delta, 'black_vega =', vega, 'black_gamma =', gamma
        print num_options, 'long and short options combined'

    def update_sabr_greeks(self):
        delta = 0.0
        vega = 0.0
        gamma = 0.0
        atm_vol = self.atm_vol
        if atm_vol == 0.0:
            return
        S = self.last(ticker_lib.futures)
        T = self.maturity()
        for ticker in self.positions:
            pos_amt = self.positions[ticker]
            if ticker == ticker_lib.futures:
                delta += pos_amt
            else:
                K, flag = ticker_lib.rev_option_tickers[ticker]
                delta += self.sabr_pricer.delta(atm_vol, S, K, T, flag)*pos_amt
                vega += self.sabr_pricer.vega(atm_vol, S, K, T, flag)*pos_amt
                gamma += self.sabr_pricer.gamma(atm_vol, S, K, T, flag)*pos_amt
        self.current_sabr_delta = delta
        self.current_sabr_vega = vega
        self.current_sabr_gamma = gamma

        print 'at money vol =', self.atm_vol
        print 'delta =', delta, 'vega =', vega, 'gamma =', gamma

    # TODO: something more intelligent than market orders
    def hedge_delta(self, order):
        try:
            if -self.delta_hedge_cutoff <= self.current_sabr_delta <= self.delta_hedge_cutoff:
                print 'skip delta hedge'
                return
            else:
                print 'hedging a delta of', self.current_sabr_delta, 'cutoff', self.delta_hedge_cutoff
                order.reserve(2)
                if self.current_sabr_delta > self.delta_hedge_cutoff:
                    size = int(self.current_sabr_delta - self.delta_hedge_cutoff)
                    self.addSell(order, ticker_lib.futures, size, 80) # market sell
                    self.current_sabr_delta -= size
                elif self.current_sabr_delta < -self.delta_hedge_cutoff:
                    size = -int(self.current_sabr_delta - self.delta_hedge_cutoff)
                    self.addBuy(order, ticker_lib.futures, size, 120) # market buy
                    self.current_sabr_delta += size
        except utils.BorrowError:
            print 'borrow error when hedging,', int(clock.monotonic() * 1000), 'ms'
            raise

    def onMarketUpdate(self, msg, order):
        Generic_Bot.onMarketUpdate(self, msg, order)

        market_state = msg['market_state']
        ticker = market_state['ticker']

        try:
            K, flag = ticker_lib.rev_option_tickers[ticker]
        except KeyError:
            # Futures, we update at-money volatility
            try:
                r = 0.3
                self.atm_vol = self.at_money_vol() * r + (1 - r) * self.atm_vol
            except KeyError:
                print 'No spot price yet:'
                print sys.exc_info()
            return

        self.sabr_pricer.add_option_price(
            self.atm_vol, self.last(ticker_lib.futures),
            K, self.maturity(), 1 * (flag == 'c'), # This prevents numpy from casting everything to strings
            self.last(ticker), 1.0)

        # TODO split this off into a function that checks a ticker for good trades
        # TODO use the liquidity in the book to size trades
        if self.limiter.amount_available() < 3:
            return
        try:
            # TODO modify fair value with fade based on existing greek exposures.
            S = self.last(ticker_lib.futures)
            T = self.maturity()
            pure_fair = self.sabr_pricer.price(self.atm_vol, S, K, T, flag)
            trade_sabr_delta = self.sabr_pricer.delta(self.atm_vol, S, K, T, flag) # delta of 1 security
            trade_sabr_vega = self.sabr_pricer.vega(self.atm_vol, S, K, T, flag)
            trade_sabr_gamma = self.sabr_pricer.gamma(self.atm_vol, S, K, T, flag)

            # impact of going long one marginal contract on the 5000 option limit
            try:
                pos_amt = self.positions[ticker]
            except KeyError:
                pos_amt = 0

            trade_num_options = 2 * sigmoid(pos_amt) - 1

            num_options_fade_offset = self.num_options_fade * self.current_num_options * trade_num_options * (
                # The fade factor smoothly increases 11x as self.current_num_options goes from 1300 to 1500, to avoid fines
                1 + 100 * sigmoid((self.current_num_options * 0.01) - 14))

            fair = pure_fair - (
                trade_sabr_delta*self.current_sabr_delta*self.sabr_delta_fade +
                trade_sabr_vega*self.current_sabr_vega*self.sabr_vega_fade +
                trade_sabr_gamma*self.current_sabr_gamma*self.sabr_gamma_fade +
                num_options_fade_offset
            )
            if fair < 0:
                print 'WARNING: CONVERTING NEGATIVE ADJUSTED FAIR PRICE TO MARKET SELL ORDER'
                fair = 0.0
            book = self.market_books[ticker]
            try:
                bid = book['sorted_bids'][0]
                if bid > fair * (1 + self.min_taking_edge):
                    size = int(self.order_size_mult)
                    order.reserve_active(1)
                    self.addTrade(order, ticker, False, size, fair * (1 + self.min_taking_edge))
                    self.current_sabr_delta -= trade_sabr_delta*size
                    self.current_sabr_vega -= trade_sabr_vega*size
                    self.current_sabr_gamma -= trade_sabr_gamma*size
                    self.current_num_options -= trade_num_options*size
                    print 'selling', size, ticker, 'for', fair * (1 + self.min_taking_edge)
            except IndexError:
                pass
            try:
                ask = book['sorted_asks'][0]
                if ask < fair * (1 - self.min_taking_edge):
                    size = int(self.order_size_mult)
                    order.reserve_active(1)
                    self.addTrade(order, ticker, True, size, fair * (1 - self.min_taking_edge))
                    print 'buying', size, ticker, 'for', fair * (1 - self.min_taking_edge)
                    self.current_sabr_delta += trade_sabr_delta*size
                    self.current_sabr_vega += trade_sabr_vega*size
                    self.current_sabr_gamma += trade_sabr_gamma*size
                    self.current_num_options += trade_num_options*size
            except IndexError:
                pass
        except utils.BorrowError:
            print 'BorrowError!'
            pass

    def onAckRegister(self, *args):
        Generic_Bot.onAckRegister(self, *args)
        def refit(order):
            print 'fitting rho and nu.'
            self.sabr_pricer.refit_model()
            self.scheduler.schedule_delay(refit, 25)
        def hedge_forever(order):
            try:
                self.hedge_delta(order)
                self.scheduler.schedule_delay(hedge_forever, 2.5)
            except utils.BorrowError:
                self.scheduler.schedule_delay(hedge_forever, 0.5)
        self.scheduler.schedule_now(hedge_forever)
        self.scheduler.schedule_delay(refit, 45)

    def onAckModifyOrders(self, msg, order):
        Generic_Bot.onAckModifyOrders(self, msg, order)

    def onTraderUpdate(self, msg, order):
        Generic_Bot.onTraderUpdate(self, msg, order)
        self.update_limited_positions()
        self.update_sabr_greeks()

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
        return self.market_books[ticker][u'last_price']
        # try:
        #     return self.mid(ticker)
        # except KeyError:
        #     return self.updated_books[ticker][u'last_price']
        # except IndexError:
        #     return self.updated_books[ticker][u'last_price']

    # Averages the at-the-money implied volatility for puts and calls, interpolating linearly between
    # the two nearest strikes
    def at_money_vol(self):
        fut_tckr = ticker_lib.futures
        spot = self.last(fut_tckr)
        try:
            return (self.market_implied_vol(spot, 'p') + self.market_implied_vol(spot, 'c')) / 2
        except ValueError:
            print self.market_books
            raise

    def market_implied_vol(self, K, option_dir):
        fut_tckr = ticker_lib.futures

        spot = self.last(fut_tckr)

        if not (80 <= K <= 120):
            print 'WARNING: NO OPTIONS WITH STRIKE PRICE', K
            K = np.clip(K, 80, 120)

        K0 = int(math.floor(K))
        K1 = int(math.ceil(K))

        opt_ticker_0 = ticker_lib.option_tickers[(K0, option_dir)]
        opt_ticker_1 = ticker_lib.option_tickers[(K1, option_dir)]
        price0 = self.last(opt_ticker_0)
        price1 = self.last(opt_ticker_1)

        T = self.maturity()

        implied_vol_0 = np.clip(ivol.implied_volatility(price0, spot, K, T, 0.0, option_dir.lower()), 0.0, None)
        implied_vol_1 = np.clip(ivol.implied_volatility(price1, spot, K, T, 0.0, option_dir.lower()), 0.0, None)

        result = (K1 - K)*implied_vol_0 + (K - K0)*implied_vol_1

        # TODO: sometimes this is zero, wtf do we do then?
        return result


