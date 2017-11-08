import tradersbot as tt
import time
import numpy
import pickle as pkl
import random
import string
import sys

i = int(sys.argv[1])
time.sleep(5)
t = tt.TradersBot(host='127.0.0.1', id='darkbot0', password='darkbot0')
tradelist = pkl.load(open('./utils/pkls/trade{0}.pkl'.format(i),'r'))
tick = 0
ticks = {}
tokens = {}
ids = {}

def f(order):
    global tick
    global tokens
    global ticks
    global ids
    
    if tick-1 in ids:
        xx = ids[tick-1]
        for cancel in xx:
            order.addCancel(cancel[1], cancel[0])
    
    token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    for pair in tradelist:
        if tick in pair:
            idx = pair[tick]['pair']
            side = pair[tick]['side']
            price = float(pair[tick]['price'])
            quantity = 1000*random.randint(8,16)
            if side == 'buy':
                order.addSell(idx, quantity=quantity, price=price, token=token)
            else:
                order.addBuy(idx, quantity=quantity, price=price, token=token)

    tokens[token] = tick
    ticks[tick] = token 
    tick += 1
    order.toJson(token)

def g(msg, order):
    global tokens
    global tick
    global ticks
    global ids
    if 'orders' in msg:
        for trade in msg['orders']:
            order_id = trade['order_id']
            ticker = trade['ticker']
            token = msg['token']
            time = tokens[token]
            if time in ids:
                ids[time].append((order_id, ticker))
            else:
                ids[time] = [(order_id,ticker)]  

t.addPeriodicCallback(f, 1000)
t.onAckModifyOrders = g
t.run()
