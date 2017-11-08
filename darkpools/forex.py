import tradersbot
import time

t = tradersbot.TradersBot('127.0.0.1', 'trader0', 'trader0')
tickers = ['USDCAD', 'EURUSD', 'USDCHF', 'USDJPY', 'EURCAD', 'EURJPY', 'EURCHF', 'CHFJPY']
print("starting")

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

openorders = {}


def marketUpdate(msg, order):
    print("market update")
    global orderbook
    global openorders
    # print(msg)
    spread = .8  # TODO figure out how to use spread better
    # spread worked best so far at 1.5
    # sets up information from the marketUpdate
    index = msg["market_state"]["ticker"]
    bids = msg["market_state"]["bids"]
    asks = msg["market_state"]["asks"]

    orderbook[index]["bids"] = bids
    orderbook[index]["asks"] = asks

    startedge = index[:3]
    endedge = index[3:]
    # the stuff above: will doing this on every update take too much time?

    if bids != {}:
        listbids = list(msg["market_state"]["bids"].keys())
        highestbid = float(listbids[listbids.index(max(listbids))])
        edges[index] = highestbid

    if asks != {}:
        listasks = list(msg["market_state"]["asks"].keys())
        lowestask = float(listasks[listasks.index(min(listasks))])
        edges[endedge + startedge] = lowestask

    for darksecurity in darktickers:
        updatedarkedges(darksecurity, order)  # update the arbitrage market prices

    # start trading after 1 second
    if time.time() - starttime > 1:
        if index == "USDCHF":
            opendarkorder('EURCHF', order, .11)  # TODO spread and quantity

        elif index == "EURUSD":
            opendarkorder('EURJPY', order, 1.5)

        elif index == 'USDJPY':
            opendarkorder('CHFJPY', order, 1.5)

        elif index == 'USDCAD':
            opendarkorder('EURCAD', order, .11)

    # delete open orders after 2.5 seconds...too many orders
    deletedorders = []
    for everyorder in openorders:
        if openorders[everyorder][0]['ticker'] in darktickers:
            if (time.time() - openorders[everyorder][1]) > 2.0:
                order.addCancel(openorders[everyorder][0]['ticker'], openorders[everyorder][0]['order_id'])
                deletedorders.append(everyorder)
        else:
            if (time.time() - openorders[everyorder][1]) > 4:
                order.addCancel(openorders[everyorder][0]['ticker'], openorders[everyorder][0]['order_id'])
                deletedorders.append(everyorder)

    for i in deletedorders:
        del openorders[i]


def updatedarkedges(darksecurity, order):
    if darksecurity == 'CHFJPY':
        edges[darksecurity] = edges[triangles[darksecurity][0]] * (1 / (edges[triangles[darksecurity][1]]))

    else:
        edges[darksecurity] = edges[triangles[darksecurity][0]] * edges[triangles[darksecurity][1]]


def opendarkorder(darksecurity, order, spread):
    """orders a dark currency at a price suitable for arbitrage"""
    """if darksecurity == 'CHFJPY':
        edges[darksecurity] = edges[triangles[darksecurity][0]] * (1/(edges[triangles[darksecurity][1]]))

    else:
        edges[darksecurity] = edges[triangles[darksecurity][0]] * edges[triangles[darksecurity][1]]"""

    if len(openorders) < 24:
        order.addTrade(darksecurity, False, 200, price=edges[darksecurity] + spread)  # 600 quantity best so far
        order.addTrade(darksecurity, True, 200, price=edges[darksecurity] - spread)


def respondDarkCompletionbuy(darksecurity, isBuy, quantity, order):
    "Responds to a dark currency being bought by selling the other two sides of the triangle"

    startedge1 = triangles[darksecurity][0][:3]
    endedge1 = triangles[darksecurity][0][3:]
    startedge2 = triangles[darksecurity][1][:3]
    endedge2 = triangles[darksecurity][1][3:]

    # CHFJPY special case
    if darksecurity == 'CHFJPY':
        order.addTrade("USDCHF", True, quantity, edges['USDCHF'])
        order.addTrade("USDJPY", False, quantity, edges['JPYUSD'])
    else:
        order.addTrade(triangles[darksecurity][0], isBuy, quantity, edges[endedge1 + startedge1])
        order.addTrade(triangles[darksecurity][1], isBuy, quantity, edges[endedge2 + startedge2])


def respondDarkCompletionsell(darksecurity, isBuy, quantity, order):
    "Responds to a dark currency being sold by buying the other two sides of the triangle"

    # CHFJPY special Case
    if darksecurity == 'CHFJPY':
        order.addTrade("USDCHF", False, quantity, edges['CHFUSD'])
        order.addTrade("USDJPY", True, quantity, edges['USDJPY'])
    else:
        order.addTrade(triangles[darksecurity][0], isBuy, quantity,
                       edges[triangles[darksecurity][0]])  # TODO which price to use, current market?
        order.addTrade(triangles[darksecurity][1], isBuy, quantity, edges[triangles[darksecurity][1]])


def periodicTraderUpdate(msg, order):
    "update the traderstate"

    global traderstate

    for item in msg["trader_state"]:
        traderstate[item] = msg["trader_state"][item]

    # print(traderstate)

    # avoiding hitting position limits
    """if traderstate['pnl']['EUR'] < 90000:
        reachingpositionlimitnegative('EUR', order)
    elif traderstate['pnl']['EUR'] > 90000:
        reachingpositionlimitpositive('EUR', order)

    if traderstate['pnl']['CAD'] < 90000:
        reachingpositionlimitnegative('CAD', order)
    elif traderstate['pnl']['EUR'] > 90000:
        reachingpositionlimitpositive('CAD', order)

    if traderstate['pnl']['EUR'] < 90000:
        reachingpositionlimitnegative('CHF', order)
    elif traderstate['pnl']['EUR'] > 90000:
        reachingpositionlimitpositive('CHF', order)

    if traderstate['pnl']['JPY'] < 9000000:
        reachingpositionlimitnegative('JPY', order)
    elif traderstate['pnl']['EUR'] > 9000000:
        reachingpositionlimitpositive('JPY', order)"""


def reachingpositionlimitpositive(currency, order):
    """converts currency back to USD to prevent reaching position limits"""
    if currency != 'EUR':
        order.addTrade("USD" + 'currency', True, 50, edges[currency + "USD"])
    else:
        order.addTrade('EURUSD', False, 50, edges["USDEUR"])


def reachingpositionlimitnegative(currency, order):
    if currency != 'EUR':
        order.addTrade('USD' + currency, False, 50, edges[currency + 'USD'])
    else:
        order.addTrade('EURUSD', True, 50, edges["EURUSD"])


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
                respondDarkCompletionbuy(ticker, False, quantity, order)  # sell the other two sides of the triangle
                del openorders[buyid]

            elif sellid in openorders:
                respondDarkCompletionsell(ticker, True, quantity, order)  # buy the other two sides of the triangle
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


def acknowledgedOrders(msg, order):
    global openorders
    print(msg)
    if 'orders' in msg:
        orders = msg["orders"]

        for eachorder in orders:  # process each order, add to openorders
            print(eachorder)
            openorders[eachorder['order_id']] = eachorder, time.time()
            print(openorders)





t.onMarketUpdate = marketUpdate
t.onAckRegister = 
t.run()

"""
Potential callbacks:

onAckRegister: MangoCore has acknowledged your registration
onMarketUpdate: an update with the orderbook and last transaction price of some single ticker
onTraderUpdate: a periodic update with your current trade state; should be already known from internal book
onTrade: a trade (not necessarily involving you) has occurred
onAckModifyOrders: MangoCore has acknowledged your order
"""
