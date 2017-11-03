# TODO fix borrows to use the semantics of PCP_Bot.addTrade and the wrapped order quota reservations
import ticker_lib
import copy
import collections
import monotonic as clock
import bot_config
import utils

class Generic_Bot:
    def __init__(self, limiter, scheduler):

        self.token_state = 0

        self.limiter = limiter
        self.scheduler = scheduler

        self.market_books = {}
        self.guess_books = {}

        self.inflight_order_tokens = set() # the set of order tokens which have not been acked
        self.active_order_tokens = set()
        self.order_token_to_id = {} # dict that maps tokens to oids
        self.order_id_to_token = {}
        self.created_orders = {} # dict that maps tokens to order records
        self.size_left = {} # dict that maps orders to their remaining size

        # these are all sets of tokens
        self.inflight_cancels = set() 
        self.tokens_to_cancel = set()
        self.retired_orders = set()

        self.cancel_retry_period = 0.25

    def addTrade(self, order, ticker, isBuy, size, price):
        order.activate()
        token = self.gen_token()
        orderArgs = (ticker, isBuy, size, price, token)
        order.addTrade(*orderArgs)
        self.inflight_order_tokens.add(token)
        self.created_orders[token] = orderArgs
        self.size_left[token] = size
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
        for ticker in internal_msg['market_states']:
            self.market_books[ticker] = {}
            self.guess_books[ticker] = {}

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

    def cancel_order(self, order, token, delay=1.0):
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

        self.market_books[ticker] = copy.deepcopy(market_state)
        self.guess_books[ticker] = copy.deepcopy(market_state)

    def onTraderUpdate(self, internal_msg, order):
        print 'onTraderUpdate'
        # TODO: track positions
        pass

    # TODO: use the time field to avoid applying trades to the guess books if the trades
    # are older than the last book update

    def onTrade(self, internal_msg, order):
        for trade in internal_msg['trades']:
            ticker = trade['ticker']
            buy_oid = trade['buy_order_id']
            sell_oid = trade['sell_order_id']
            qty = trade['quantity']
            price = trade['price']
            for oid in [buy_oid, sell_oid]:
                if oid in self.order_id_to_token:
                    token = self.order_id_to_token[oid]
                    self.size_left[token] -= qty
                    if self.size_left[token] == 0:
                        self.active_order_tokens.remove(token)
                        self.tokens_to_cancel.remove(token)
                        self.retired_orders.add(token)
            guess_book = self.guess_books[ticker]

            # remove bids that must have traded
            bids = self.guess_book['bids']
            for i in xrange(len(self.guess_book['sorted_bids'])):
                bid = self.guess_book['sorted_bids'][i]
                if bid > price:
                    bids.pop(bid)
                    continue
                else:
                    self.guess_book['sorted_bids'] = self.guess_book['sorted_bids'][i:]
                    break
            bid = self.guess_book['sorted_bids'][0]
            if bid == price:
                if bids[bid] == qty:
                    bids.pop(bid)
                    self.guess_book['sorted_bids'] = self.guess_book['sorted_bids'][1:]
                else:
                    bids[bid] -= qty

            # remove asks that must have traded
            asks = self.guess_book['asks']
            for i in xrange(len(self.guess_book['sorted_asks'])):
                ask = self.guess_book['sorted_asks'][i]
                if ask < price:
                    asks.pop(ask)
                    continue
                else:
                    self.guess_book['sorted_asks'] = self.guess_book['sorted_asks'][i:]
                    break
            ask = self.guess_book['sorted_asks'][0]
            if ask == price:
                if asks[ask] == qty:
                    asks.pop(ask)
                    self.guess_book['sorted_asks'] = self.guess_book['sorted_asks'][1:]
                else:
                    asks[ask] -= qty

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
