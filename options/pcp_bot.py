# TODO fix borrows to use the semantics of PCP_Bot.addTrade and the wrapped order quota reservations
import ticker_lib
import copy
import collections
import monotonic as clock
import bot_config
import utils

class PCP_Bot:
    def __init__(self, limiter, scheduler):

        config = bot_config.PCP

        self.cancel_retry_period = config.cancel_retry_period

        self.token_state = 0
        self.token_prefix = config.token_prefix

        self.limiter = limiter
        self.scheduler = scheduler

        self.staleness_cutoff = config.staleness_cutoff_seconds
        self.size_factor = config.size_factor
        self.min_edge = config.min_edge
        self.books = {}
        self.my_orders = {}
        self.last_update = {}
        self.recently_updated = collections.deque()

        self.inflight_order_tokens = set() # the set of order tokens which have not been acked
        self.active_order_tokens = set()
        self.order_token_to_id = {} # dict that maps tokens to oids
        self.order_id_to_token = {}
        self.created_orders = {} # dict that maps tokens to order records

        # these are all sets of tokens
        self.inflight_cancels = set() 
        self.tokens_to_cancel = set()
        self.retired_orders = set()

    def addTrade(self, order, ticker, isBuy, size, price):
        order.activate()
        token = self.gen_token()
        orderArgs = (ticker, isBuy, size, price, token)
        order.addTrade(*orderArgs)
        self.inflight_order_tokens.add(token)
        self.created_orders[token] = orderArgs
        return token

    def addBuy(self, order, ticker, size, price):
        return self.addTrade(order, ticker, True, size, price)

    def addSell(self, order, ticker, size, price):
        return self.addTrade(order, ticker, False, size, price)

    def addCancel(self, order, ticker, oid):
        order.activate()
        order.cancel(ticker, oid)

    def gen_token(self):
        self.token_state += 1
        return self.token_prefix + ':PCP_Bot_token:' + str(self.token_state)

    def onAckRegister(self, internal_msg, order):
        ts = clock.monotonic()
        try:
            for ticker in internal_msg['market_states']:
                self.books[ticker] = {}
                self.last_update[ticker] = ts
        except KeyError as e:
            print e
            print internal_msg
            raise e

    # def retry_while_BorrowError(delay):
    #     def deco(f):
    #         def wrapper(self, order, *args):
    #             try:
    #                 f(self, order, *args)
    #             except utils.BorrowError:
    #                 self.schedule_delay(wrapper, delay)
    #         return wrapper
    #     return deco


    def cancel_active_order(self, order, token, oid):
        def bare_cancel():
            ticker = self.created_orders[token][0]
            order.reserve_active(1)
            self.addCancel(self, order, ticker, oid)
        def wrapper(order):
            try:
                bare_cancel()
            except utils.BorrowError:
                self.schedule_delay(wrapper, self.cancel_retry_period)

    def cancel_token(self, order, token, delay=1.0):
        if token in active_order_ids:
            oid = active_order_ids[token]
            self.cancel_active_order(order, token, oid)
        else:
            self.tokens_to_cancel.add(token)

    def onMarketUpdate(self, internal_msg, order):
        print 'onMarketUpdate'
        ts =  clock.monotonic()
        market_state = internal_msg['market_state']
        ticker = market_state['ticker']

        while self.recently_updated and self.last_update[self.recently_updated[0]] < ts - self.staleness_cutoff:
            self.recently_updated.popleft()

        self.recently_updated.append(ticker)
        self.last_update[ticker] = ts

        self.books[ticker] = copy.deepcopy(market_state)

        try:
            print 'Can we refresh arbs?'
            order.reserve_active(2) # no point in running any of this crap unless we can send one of our orders
        except utils.BorrowError:
            return

        if ticker == ticker_lib.futures:
            non_stale_tickers = set(self.recently_updated)
            all_strikes = (ticker_lib.rev_option_tickers[tck][0] for tck in non_stale_tickers if tck != ticker_lib.futures)
            non_stale_strikes = set(k for k in all_strikes if \
                                    ticker_lib.option_tickers[(k, 'P')] in non_stale_tickers and \
                                    ticker_lib.option_tickers[(k, 'C')] in non_stale_tickers)
            delta_if_filled = 0
            tokens = []
            for strike in non_stale_strikes:
                try:
                    new_delta, new_tokens = self.refresh_arb(strike, order)
                except utils.BorrowError:
                    break
                delta_if_filled += new_delta
                tokens += new_tokens

            self.scheduler.scheduler(self.make_canceler(tokens, 1.0))

        else:
            if self.last_update[ticker_lib.futures] < ts - self.staleness_cutoff:
                return
            k, d = ticker_lib.rev_option_tickers[ticker]
            d2 = ticker_lib.other_dir[d]
            ticker2 = ticker_lib.option_tickers[(k, d2)]
            if self.last_update[ticker] < ts - self.staleness_cutoff:
                return
            try:
                delta_if_filled, tokens = self.refresh_arb(k, order)
            except utils.BorrowError:
                pass

    def refresh_arb(self, strike, order):
        call_ticker = ticker_lib.option_tickers[(strike, 'C')]
        call_book = self.books[call_ticker]

        put_ticker = ticker_lib.option_tickers[(strike, 'P')]
        put_book  = self.books[put_ticker]

        fut_ticker = ticker_lib.futures
        fut_book  = self.books[ticker_lib.futures]

        # Check for PCP arb in the buy-synthetic-forward direction
        try:
            put_bid = put_book['sorted_bids'][0]
            put_bid_sz = put_book['bids'][put_bid]
            call_ask = call_book['sorted_asks'][0]
            call_ask_sz = call_book['asks'][call_ask]
            fut_bid = fut_book['sorted_bids'][0]
            fut_bid_sz = fut_book['bids'][fut_bid]

            delta_is_cheap = strike*(1 + self.min_edge) < put_bid - call_ask + fut_bid
        except IndexError:
            delta_is_cheap = False
        except KeyError:
            delta_is_cheap = False

        if delta_is_cheap:
            size = self.size_factor * min(put_bid_sz, call_ask_sz, fut_bid_sz)
            print 'PCP ARB: buying', size, 'delta at strike', strike, 'with edge =', (put_bid - call_ask + fut_bid)/strike
            print call_ticker, put_ticker
            self.limiter.borrow(2)
            token1 =  self.addBuy(order, call_ticker, size, call_ask)
            token2 = self.addSell(order, put_ticker,  size, put_bid)
            return (size, [token1, token2])
        else:
            try:
                call_bid = call_book['sorted_bids'][0]
                call_bid_sz = call_book['bids'][call_bid]
                put_ask = put_book['sorted_asks'][0]
                put_ask_sz = put_book['asks'][put_ask]
                fut_ask = fut_book['sorted_asks'][0]
                fut_ask_sz = fut_book['asks'][fut_ask]

                delta_is_rich = strike*(1 - self.min_edge) > put_ask - call_bid - fut_ask
            except IndexError:
                return (0, [])
            except KeyError:
                return (0, [])
            if delta_is_rich:
                size = self.size_factor * min(put_bid_sz, call_ask_sz, fut_bid_sz)
                print 'PCP ARB: selling', size, 'delta at strike', strike, 'with edge =',  (put_ask - call_bid - fut_ask)/strike
                print call_ticker, put_ticker
                self.limiter.borrow(2)
                token1 = self.addSell(order, call_ticker, size, call_bid)
                token2 = self.addBuy(order, put_ticker, size, put_ask)
                return (-size, [token1, token2])
            else:
                return (0, [])

    def onTraderUpdate(self, internal_msg, order):
        print 'onTraderUpdate'
        # TODO: track positions
        pass

    def onTrade(self, internal_msg, order):
        print 'onTrade'
        # TODO: remove fully filled orders from the sets of active orders and orders to cancel
        pass

    def onAckModifyOrders(self, internal_msg, order):
        print 'onAckModifyOrders'
        for cancel in internal_msg['cancels']:
            for oid in cancel:
                token = self.order_id_to_token[oid]
                self.active_order_tokens.remove(token)
                self.inflight_cancels.remove(token)
            self.inflight_cancels.remove()
        for order_data in internal_msg['orders']:
            token = order_data['token']
            oid = order_data['order_id']
            self.order_token_to_id[token] = oid
            self.order_id_to_token[oid] = token
            del self.inflight_order_tokens[token]
