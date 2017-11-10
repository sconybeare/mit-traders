import tradersbot
import time

t = tradersbot.TradersBot('127.0.0.1', 'trader0', 'trader0')
tickers = ['USDCAD', 'EURUSD', 'USDCHF', 'USDJPY', 'EURCAD', 'EURJPY', 'EURCHF', 'CHFJPY']
print("starting")

# the book as we know it
orderbook = dict(USDCAD={"bids": {}, "asks": {}}, USDJPY={"bids": {}, "asks": {}}, EURUSD={"bids": {}, "asks": {}},
                 USDCHF={"bids": {}, "asks": {}}, CHFJPY={"bids": {}, "asks": {}}, EURJPY={"bids": {}, "asks": {}},
                 EURCHF={"bids": {}, "asks": {}}, EURCAD={"bids": {}, "asks": {}})

# spring constants for the bias towards USD
springs = dict(CAD=1, JPY=1, EUR=1, CHF=1)

# everything we need to know about our state of being
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

openorders = {}


def market_update(msg, order):
    global orderbook
    global openorders

    index = msg["market_state"]["ticker"]
    bids = msg["market_state"]["bids"]
    asks = msg["market_state"]["asks"]

    orderbook[index]["bids"] = bids
    orderbook[index]["asks"] = asks

    startedge = index[:3]
    endedge = index[3:]

    if bids != {}:
        listbids = list(msg["market_state"]["bids"].keys())
        highestbid = float(listbids[listbids.index(max(listbids))])
        edges[index] = highestbid

    if asks != {}:
        listasks = list(msg["market_state"]["asks"].keys())
        lowestask = float(listasks[listasks.index(min(listasks))])
        edges[endedge + startedge] = lowestask

    for darksecurity in darktickers:
        update_dark_edges(darksecurity, order)


    if index == "USDCHF":
        open_dark_order('EURCHF', order, .15)

    elif index == "EURUSD":
        open_dark_order('EURJPY', order, .95)

    elif index == 'USDJPY':
        open_dark_order('CHFJPY', order, 1.2)

    elif index == 'USDCAD':
        open_dark_order('EURCAD', order, .1)


    # clean open orders
    deletedorders = []
    for elem in openorders:
        if openorders[elem][0]['ticker'] in darktickers:
            if (time.time() - openorders[elem][1]) > 2.0:
                order.addCancel(openorders[elem][0]['ticker'], openorders[elem][0]['order_id'])
                deletedorders.append(elem)
        else:
            if (time.time() - openorders[elem][1]) > 4.0:
                order.addCancel(openorders[elem][0]['ticker'], openorders[elem][0]['order_id'])
                order.addTrade(openorders[elem][0]['ticker'], openorders[elem][0]['buy'],openorders[elem][0]['quantity'])
                deletedorders.append(elem)

    for i in deletedorders:
        del openorders[i]

    update_springs()


def update_springs():
    print("update springs")


def update_dark_edges(darksecurity, order):
    if darksecurity == 'CHFJPY':
        if not edges[triangles[darksecurity][1]] == 0:
            edges[darksecurity] = edges[triangles[darksecurity][0]] * (1 / (edges[triangles[darksecurity][1]]))
        else:
            print("saved divide by zero")

    else:
        edges[darksecurity] = edges[triangles[darksecurity][0]] * edges[triangles[darksecurity][1]]


def open_dark_order(darksecurity, order, spread):

    if len(openorders) < 30:
        order.addTrade(darksecurity, False, 200, edges[darksecurity] + spread)
        order.addTrade(darksecurity, True, 200, edges[darksecurity] - spread)


def respond_dark_completion_buy(darksecurity, is_buy, quantity, order):
    "Responds to a dark currency being bought by selling the other two sides of the triangle"

    startedge1 = triangles[darksecurity][0][:3]
    endedge1 = triangles[darksecurity][0][3:]
    startedge2 = triangles[darksecurity][1][:3]
    endedge2 = triangles[darksecurity][1][3:]

    if darksecurity == 'CHFJPY':
        order.addTrade("USDCHF", True, quantity, edges['USDCHF'])
        order.addTrade("USDJPY", False, quantity, edges['JPYUSD'])
    else:
        order.addTrade(triangles[darksecurity][0], is_buy, quantity, edges[endedge1 + startedge1])
        order.addTrade(triangles[darksecurity][1], is_buy, quantity, edges[endedge2 + startedge2])


def respond_dark_completion_sell(darksecurity, is_buy, quantity, order):
    "Responds to a dark currency being sold by buying the other two sides of the triangle"

    if darksecurity == 'CHFJPY':
        order.addTrade("USDCHF", False, quantity, edges['CHFUSD'])
        order.addTrade("USDJPY", True, quantity, edges['USDJPY'])
    else:
        order.addTrade(triangles[darksecurity][0], is_buy, quantity, edges[triangles[darksecurity][0]])
        order.addTrade(triangles[darksecurity][1], is_buy, quantity, edges[triangles[darksecurity][1]])


def reactOnTrade(msg, order):
    global orderbook
    global openorders
    # print(msg)

    for trade in msg["trades"]:
        buyid = "arbitrary"
        sellid = "arbitrary"
        ticker = trade["ticker"]
        price = trade["price"]
        quantity = trade["quantity"]
        if 'buy_order_id' in trade:
            buyid = trade['buy_order_id']
        if 'sell_order_id' in trade:
            sellid = trade['sell_order_id']

        # trading the triangle
        if ticker in darktickers:
            if buyid in openorders:
                respond_dark_completion_buy(ticker, False, quantity, order)  # sell the other two sides of the triangle
                del openorders[buyid]

            elif sellid in openorders:
                respond_dark_completion_sell(ticker, True, quantity, order)  # buy the other two sides of the triangle
                del openorders[sellid]

        # if other orders completed, take them out of the openorders
        else:
            if buyid in openorders:  # delete the order if it succeeds
                del openorders[buyid]

            elif sellid in openorders:  # delete the order if it succeeds
                del openorders[sellid]

        try:
            if msg["trades"]["buy"] == True:
                if price in orderbook[ticker]["bids"]:
                    orderbook[ticker]["bids"][price] = orderbook[ticker]["bids"][price] - quantity
                    if orderbook[ticker]["bids"][price] == 0:
                        orderbook[ticker]["bids"].pop(price, None)
            else:
                if price in orderbook[ticker]["asks"]:
                    orderbook[ticker]["asks"][price] = orderbook[ticker]["asks"][price] - quantity
                    if orderbook[ticker]["asks"][price] == 0:
                        orderbook[ticker]["asks"].pop(price, None)
        except:
            pass  # just so things run for now...


def acknowledged_orders(msg, order):
    global openorders

    if 'orders' in msg:
        orders = msg["orders"]

        for elem in orders:  # process each order, add to openorders
            openorders[elem['order_id']] = elem, time.time()


def verify_trader_state(msg, order):
    print(msg)
    global traderstate

    for elem in msg["trader_state"]:
        traderstate[elem] = msg["trader_state"][elem]


t.onMarketUpdate = market_update
t.onTraderUpdate = verify_trader_state
t.onTrade = reactOnTrade
t.onAckModifyOrders = acknowledged_orders
t.run()

# u'positions': {u'EURJPY': 0, u'CHFJPY': -200, u'USDCHF': 0, u'EURCHF': 0, u'EURCAD': 0, u'EURUSD': 0, u'USDJPY': 0, u'USDCAD': 0}
# u'cash': {u'JPY': 22622, u'EUR': 0, u'USD': 100000, u'CHF': -200, u'CAD': 0}