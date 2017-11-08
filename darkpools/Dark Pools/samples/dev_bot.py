import tradersbot as tt
import math
import random

t = tt.TradersBot(host='127.0.0.1', id='trader0', password='trader0')
tick = 0
tickers = ['USDCHF','USDJPY','EURUSD','USDCAD','CHFJPY','EURJPY','EURCHF','EURCAD' ]

def get_side():
    return 'buy' if random.random() > 0.5 else 'sell'

def f(msg, order):    
    global tick
    quantity = 500
    idx = 'USDCHF'
    side = get_side()
    if side == 'buy':
        order.addBuy(idx, quantity=quantity, price=0.99)
    else:
        order.addSell(idx, quantity=quantity, price=1.01) 

    tick += 1
    print('Traded')

t.onMarketUpdate = f
t.run()
