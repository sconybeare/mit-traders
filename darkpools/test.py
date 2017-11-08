from tradersbot import TradersBot as TB

t = TB('127.0.0.1', 'trader0', 'trader0')
t.run()


tickers = ['USDCAD', 'EURUSD', 'USDCHF', 'USDJPY', 'EURCAD', 'EURJPY', 'EURCHF', 'CHFJPY']

# the book as we know it
orderbook = dict(USDCAD={"bids": {}, "asks": {}}, USDJPY={"bids": {}, "asks": {}}, EURUSD={"bids": {}, "asks": {}},
                 USDCHF={"bids": {}, "asks": {}}, CHFJPY={"bids": {}, "asks": {}}, EURJPY={"bids": {}, "asks": {}},
                 EURCHF={"bids": {}, "asks": {}}, EURCAD={"bids": {}, "asks": {}})

# everything we need to know about our state of being
# TODO replace this with the generic_bot code
traderstate = {'cash': {"USD": 100000}, 'positions': {}, 'open_orders': {}, 'pnl': {"USD": 0}, 'time': '1',
               'total_fees': 0, 'total_fines': 0, 'total_rebates': 0}

# just the dark pools
darktickers = ['EURCHF', 'EURCAD', 'EURJPY', 'CHFJPY']

# all edges as they appear in the exchange
edges = {'USDCAD': 0, 'EURUSD': 0, 'USDCHF': 0, 'USDJPY': 0, 'EURCAD': 0, 'EURJPY': 0, 'EURCHF': 0, 'CHFJPY': 0,
         'CADUSD': 0, 'USDEUR': 0, 'CHFUSD': 0, 'JPYUSD': 0, 'CADEUR': 0, 'JPYEUR': 0, 'CHFEUR': 0, 'JPYCHF': 0}

# by dark pool order
triangles = {'EURCHF': ('USDCHF', 'EURUSD'), 'EURCAD': ('USDCAD', 'EURUSD'),
             'EURJPY': ('USDJPY', 'EURUSD'), 'CHFJPY': ('USDJPY', 'USDCHF')}


def makeTrades():



