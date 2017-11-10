import tradersbot as tt
from sabr_bot import SABR_Bot
import utils

import config

t = tt.TradersBot(host=config.host, id=config.id, password=config.password))

rate_limiter = utils.RateLimiter(90, 1.523) # fudge factor deliberately not divisible by polling rate, and we limit to 20 just to be safe
scheduler = utils.Scheduler()

order_wrapper = utils.OrderWrapper(rate_limiter)

strats = [SABR_Bot(rate_limiter, scheduler)]

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
    for s in strats:
        s.onTrade(msg, order)

@order_wrapper.dec
def onAckModifyOrders(msg, order):
    for s in strats:
        s.onAckModifyOrders(msg, order)

def periodicCallback(order):
    scheduler.run(order_wrapper.wrap(order))

if __name__ == '__main__':
    t.onMarketUpdate = onMarketUpdate
    t.onTraderUpdate = onTraderUpdate
    t.onAckRegister = onAckRegister
    t.onTrade = onTrade
    t.onAckModifyOrders = onAckModifyOrders
    t.addPeriodicCallback(periodicCallback, 50)
    t.run()
