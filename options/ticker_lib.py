strikes = range(80, 121)
option_dirs = ['p', 'c']

other_dir = {'p' : 'c', 'c' : 'p'}

# Internally, we treat options as tuples
option_tickers = {(K, d) : 'T' + str(K) + d.upper() for K in strikes for d in option_dirs}
rev_option_tickers = {'T' + str(K) + d.upper() : (K, d) for K in strikes for d in option_dirs}

futures = 'TMXFUT'
