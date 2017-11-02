import tradersbot as tt
import math
import random
import sys
import csv
import json

t = tt.TradersBot(host='127.0.0.1', id='trader0', password='trader0')
tick = 0
strikes = range(80, 121)
option_dirs = ['P', 'C']

# Internally, we treat options as tuples
option_tickers = {(K, d) : 'T' + str(K) + d for K in strikes for d in option_dirs}
rev_option_tickers = {'T' + str(K) + d : (K, d) for K in strikes for d in option_dirs}

futures = 'TMXFUT'

for k in option_tickers:
    assert rev_option_tickers[option_tickers[k]] == k

for k in rev_option_tickers:
    assert option_tickers[rev_option_tickers[k]] == k

filename = sys.argv[1]
outfile = open(filename, 'w')

msgs = []

# The goal here is to get price tick data for the case.
def f(msg, order):
    global tick
    msg['tick'] = tick
    json.dump(msg, outfile)
    tick += 1

    # global tick
    # quantity = 500
    # idx = 'USDCAD'
    # side = get_side()
    # if side == 'buy':
    #     order.addBuy(idx, quantity=quantity, price=0.99)
    # else:
    #     order.addSell(idx, quantity=quantity, price=1.01)

    # tick += 1
    # print('Traded')

t.onMarketUpdate = f
t.run()
