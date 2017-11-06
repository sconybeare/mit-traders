import vollib.black_scholes.implied_volatility as ivol
import vollib.black_scholes.greeks.analytical as greeks
import vollib.black_scholes as bs
import numpy as np
import scipy.optimize as scp_opt
import monotonic as clock

class SabrPricer(object):
    def __init__(self, beta=0.5):
        self.model = SabrModel(beta=beta)

    def add_trade(self, *args):
        self.model.add_trade(*args)

    def get_vol(self, atm_vol, S, K, T):
        return sabr_implied_vol(atm_vol, self.model.beta, self.model.beta, self.model.rho, self.model.nu, S, K, T)

    def price(self, atm_vol, S, K, T, flag):
        vol = self.get_vol(atm_vol, S, K, T)
        return bs.black_scholes(flag, S, K, T, 0.0, vol)

    def delta(self, atm_vol, S, K, T, flag):
        vol = self.get_vol(atm_vol, S, K, T)
        return greeks.delta(flag, S, K, T, 0.0, vol)

    def vega(self, atm_vol, S, K, T, flag):
        vol = self.get_vol(atm_vol, S, K, T)
        return greeks.vega(flag, S, K, T, 0.0, vol)

# TODO check whether refitting is expensive enough to warrant multiprocessing
class SabrModel(object):
    def __init__(self, beta=0.5):
        self.beta = beta
        self.opt_trade_data = []
        self.current_spot_price = None
        self.rho = 0.0
        self.nu = 0.1

    # If we had real trade data, weight would equal the number of shares traded at that price
    # Events should be added in the order they happen
    def add_option_price(self, vol_atm, S, K, tau, flag, price, weight):
        self.opt_trade_data.append((vol_atm, S, K, tau, flag.lower(), price, weight))

    def fit_rho_nu(self):
        t0 = clock.monotonic()
        trades = np.array(self.opt_trade_data)
        vectorized_data = trades.transpose()

        # these are all numpy vectors giving these parameters of every data point
        [vol_atm, S, K, tau, flag, price, weight] = cpts

        rho_bounds = (-1.0, 1.0)
        nu_bounds = (0.01, None)

        def err(rho_nu):
            rho, nu = rho_nu
            rho = np.clip(rho, *rho_bounds)
            nu = np.clip(nu, *nu_bounds)
            alpha = compute_alpha(vol_atm, tau, S, self.beta, rho, nu)
            sigma_mod = sabr_implied_vol_with_alpha(alpha, self.beta, rho, nu, S, K, tau)
            sigma_tr = np.clip(ivol.implied_volatility(price, S, K, tau, 0.0, flag), 0.0, None)
            vega_mod = greeks.vega(flag, S, K, tau, 0.0, sigma_mod)
            f = weight * vega_mod * (sigma_mod - sigma_tr) ** 2
            return np.sum(f)

        rho, nu = scp_opt.minimize(err, (self.rho, self.nu), method='Nelder-Mead', bounds=[rho_bounds, nu_bounds])
        t1 = clock.monotonic()
        print 'fitted rho and nu taking time' + str(t1 - t0) + 'with' + str(len(self.opt_trade_data)) + 'data points'
        self.rho = rho
        self.nu = nu

def sabr_implied_vol(atm_vol, beta, rho, nu, S, K, T):
    alpha = compute_alpha(atm_implied_vol, T, S, beta, rho, nu)
    return sabr_implied_vol_with_alpha(alpha, beta, rho, nu, S, K, T)

def sabr_implied_vol_with_alpha(alpha, beta, rho, nu, F, K, T):
    zeta = (nu / (alpha*(1 - beta))) * (F_0**(1-beta) - K**(1-beta))
    D_zeta = np.log(
        (np.sqrt(1 - 2*rho*zeta + zeta**2) + zeta - rho
        ) / (1 - rho))
    F_mid = np.sqrt(F_0 * K)
    gamma_1 = beta / F_mid
    gamma_2 = - beta*(1 - beta) / F_mid**2
    epsilon = T * nu**2
    one_plus_epsilon_term = 1 + (
        ((2*gamma_2 - gamma_1**2 + 1/F_mid**2) / 24
        )*((alpha * F_mid**beta / nu) ** 2)
        +
        (rho*gamma_1 / 4) * (alpha * F_mid**beta / nu)
        +
        (2 - 3*rho**2) / 24
    )*epsilon

    return nu * (np.log(F_0 / K) / D_zeta) * one_plus_epsilon_term


# TODO: If the rho_nu error fitting has numpy array issues, try vectorizing this manually.
@np.vectorize
def compute_alpha(atm_implied_vol, tau, spot, beta, rho, nu):
    F_b = spot ** (1 - beta)
    coeff_3 = (1 - beta)**2 * tau / (24 * F_b ** 2)
    coeff_2 = rho * beta * nu * tau / (4 * F_b)
    coeff_1 = 1 + (2 - 3*rho**2) * nu**2 * tau / 24
    coeff_0 = - atm_implied_vol * F_b

    a = coeff_2 / coeff_3
    b = coeff_1 / coeff_3
    c = coeff_0 / coeff_3

    # Numerically stable version of Tartaglia's method from the book Numerical Recipes in C
    Q = (a**2 - 3*b) / 9
    R = (2*a**3 - 9*a*b + 27*c) / 54

    # If there are 3 real roots
    if R**2 < Q**3:
        theta = np.arccos(R / Q ** 1.5)
        # the roots are
        r1 = -2 * np.sqrt(Q) * np.cos(theta / 3) - a / 3
        r2 = -2 * np.sqrt(Q) * np.cos((theta + 2*np.pi) / 3) - a / 3
        r3 = -2 * np.sqrt(Q) * np.cos((theta - 2*np.pi) / 3) - a / 3

        # return the smallest positive real root
        return min(x for x in [r1, r2, r3] if x > 0)
    else:
        A = -np.sign(R) * (np.abs(R) + np.sqrt(R**2 - Q**3))**(1.0 / 3)
        B = if A == 0.0 then 0 else Q / A

        # return the unique real root
        return A + B - a / 3
