strikes = range(80, 121)
option_dirs = ['P', 'C']

other_dir = {'P' : 'C', 'C' : 'P'}

# Internally, we treat options as tuples
option_tickers = {(K, d) : 'T' + str(K) + d for K in strikes for d in option_dirs}
rev_option_tickers = {'T' + str(K) + d : (K, d) for K in strikes for d in option_dirs}

futures = 'TMXFUT'
