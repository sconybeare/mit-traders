import tradersbot as tt
import math
import random
import sys
import csv
import json

# Local imports
import pcp_bot
import utils

t = tt.TradersBot(host='127.0.0.1', id='trader0', password='trader0')

rate_limiter = utils.RateLimiter(25, 1.5) # 1.1 second fudge factor, since our timing is different from exchange's
scheduler = utils.Scheduler()

order_wrapper = utils.OrderWrapper(rate_limiter)

pcp_bot = pcp_bot.PCP_Bot(rate_limiter, scheduler)

strats = [pcp_bot]

@order_wrapper.dec
def onAckRegister(msg, order):
    for ticker in msg['market_states']:
        utils.convert_market_state(msg['market_states'][ticker])
    for s in strats:
        s.onAckRegister(msg, order)

@order_wrapper.dec
def onMarketUpdate(msg, order):
    try:
        assert 'market_state' in msg
        utils.convert_market_state(msg['market_state'])
    except:
        print 'MESSAGE NOT CONTAINING \'market_state\''
        print msg
        raise

    for s in strats:
        s.onMarketUpdate(msg, order)

@order_wrapper.dec
def onTraderUpdate(msg, order):
    for s in strats:
        s.onTraderUpdate(msg, order)

@order_wrapper.dec
def onTrade(msg, order):
    print msg
    for s in strats:
        s.onTrade(msg, order)

@order_wrapper.dec
def onAckModifyOrders(msg, order):
    print msg
    for s in strats:
        s.onAckModifyOrders(msg, order)

def periodicCallback(order):
    print rate_limiter.amount_available()
    scheduler.run(order_wrapper.wrap(order))

if __name__ == '__main__':
    print 'hello, world!'
    t.onMarketUpdate = onMarketUpdate
    t.onTraderUpdate = onTraderUpdate
    t.onAckRegister = onAckRegister
    t.onTrade = onTrade
    t.onAckModifyOrders = onAckModifyOrders
    t.addPeriodicCallback(periodicCallback, 500)
    t.run()
