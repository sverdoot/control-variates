import torch
from torch.optim import Optimizer

from numpy.random import gamma


class LangevinSGD(Optimizer):
    def __init__(self, params, lr, weight_decay=0, nesterov=False):
        if lr < 0.0:
            raise ValueError("Invalid learning rate: {}".format(lr))
        if weight_decay < 0.0:
            raise ValueError("Invalid weight_decay value: {}".format(weight_decay))

        defaults = dict(lr=lr, weight_decay=weight_decay)

        super(LangevinSGD, self).__init__(params, defaults)

    def __setstate__(self, state):
        super(LangevinSGD, self).__setstate__(state)
        for group in self.param_groups:
            group.setdefault('nesterov', False)

    @torch.no_grad()
    def step(self, closure=None):

        loss = None
        if closure is not None:
            with torch.enable_grad():
                loss = closure()

        for group in self.param_groups:

            weight_decay = group['weight_decay']

            for p in group['params']:
                if p.grad is None:
                    continue
                d_p = p.grad

                if weight_decay != 0:
                    d_p.add_(p.data, alpha=weight_decay)

                unit_noise = p.new_empty(p.size()).normal_()
                p.add_(0.5 * d_p + unit_noise / group['lr'] ** 0.5, alpha=-group['lr'])
        return loss


class SGHMC_SA(Optimizer):
    """ Stochastic Gradient Hamiltonian Monte-Carlo Sampler that uses scale adaption during burn-in
        procedure to find some hyperparamters. A gaussian prior is placed over parameters and a Gamma
        Hyperprior is placed over the prior's standard deviation

        See [1] for more details on this burn-in procedure.\n
        See [2] for more details on Stochastic Gradient Hamiltonian Monte-Carlo.

        [1] J. T. Springenberg, A. Klein, S. Falkner, F. Hutter
            In Advances in Neural Information Processing Systems 29 (2016).\n
            `Bayesian Optimization with Robust Bayesian Neural Networks. <http://aad.informatik.uni-freiburg.de/papers/16-NIPS-BOHamiANN.pdf>`_
        [2] T. Chen, E. B. Fox, C. Guestrin
            In Proceedings of Machine Learning Research 32 (2014).\n
            `Stochastic Gradient Hamiltonian Monte Carlo <https://arxiv.org/pdf/1402.4102.pdf>`_
        """

    def __init__(self, params, lr: float = 1e-2, base_c: float = 0.05, gauss_sig: float = 0.1, alpha0: float = 10, beta0: float = 10):
        """
        Set up the optimizer

        :param params: Iterable, parameters serving as optimization variables
        :param lr: float, learning
        :param base_c: float, friction term
        :param gauss_sig: float, initial prior sigma
        :param alpha0: float, initial hyperprior
        :param beta0: flaot, initial hyperprior
        """
        self.eps = 1e-6
        self.alpha0 = alpha0
        self.beta0 = beta0

        if gauss_sig == 0:
            self.weight_decay = 0
        else:
            self.weight_decay = 1 / (gauss_sig ** 2)

        if self.weight_decay <= 0.0:
            raise ValueError("Invalid weight_decay value: {}".format(self.weight_decay))
        if lr < 0.0:
            raise ValueError("Invalid learning rate: {}".format(lr))
        if base_c < 0:
            raise ValueError("Invalid friction term: {}".format(base_c))

        defaults = dict(
            lr=lr,
            base_c=base_c,
        )
        super(SGHMC_SA, self).__init__(params, defaults)

    def step(self, burn_in=False, resample_momentum=False, resample_prior=False):
        """Simulate discretized Hamiltonian dynamics for one step"""
        loss = None

        for group in self.param_groups:  # iterate over blocks -> the ones defined in defaults. We dont use groups.
            for p in group["params"]:  # these are weight and bias matrices
                if p.grad is None:
                    continue
                state = self.state[p]  # define dict for each individual param
                if len(state) == 0:
                    state["iteration"] = 0
                    state["tau"] = torch.ones_like(p)
                    state["g"] = torch.ones_like(p)
                    state["V_hat"] = torch.ones_like(p)
                    state["v_momentum"] = torch.zeros_like(
                        p)  # p.data.new(p.data.size()).normal_(mean=0, std=np.sqrt(group["lr"])) #
                    state['weight_decay'] = self.weight_decay

                state["iteration"] += 1  # this is kind of useless now but lets keep it provisionally

                if resample_prior:
                    alpha = self.alpha0 + p.data.nelement() / 2
                    beta = self.beta0 + (p.data ** 2).sum().item() / 2
                    gamma_sample = gamma(shape=alpha, scale=1/beta, size=None)
                    #                     print('std', 1/np.sqrt(gamma_sample))
                    state['weight_decay'] = gamma_sample

                base_c, lr = group["base_C"], group["lr"]
                weight_decay = state["weight_decay"]
                tau, g, v_hat = state["tau"], state["g"], state["V_hat"]

                d_p = p.grad
                if weight_decay != 0:
                    d_p.add_(p.data, alpha=weight_decay)

                # update parameters during burn-in
                if burn_in:  # We update g first as it makes most sense
                    tau.add_(-tau * (g ** 2) /
                             (v_hat + self.eps) + 1)  # specifies the moving average window, see Eq 9 in [1] left
                    tau_inv = 1. / (tau + self.eps)
                    g.add_(-tau_inv * g + tau_inv * d_p)  # average gradient see Eq 9 in [1] right
                    v_hat.add_(-tau_inv * v_hat + tau_inv * (d_p ** 2))  # gradient variance see Eq 8 in [1]

                v_sqrt = torch.sqrt(v_hat)
                v_inv_sqrt = 1. / (v_sqrt + self.eps)  # preconditioner

                if resample_momentum:  # equivalent to var = M under momentum reparametrisation
                    state["v_momentum"] = torch.normal(mean=torch.zeros_like(d_p),
                                                       std=lr * v_inv_sqrt)
                v_momentum = state["v_momentum"]

                noise_var = (2. * (lr ** 3) * v_inv_sqrt * base_c * v_inv_sqrt - (lr ** 4))
                noise_std = torch.sqrt(torch.clamp(noise_var, min=1e-16))
                # sample random epsilon
                noise_sample = torch.normal(mean=torch.zeros_like(d_p), std=noise_std)

                # update momentum (Eq 10 right in [1])
                v_momentum.add_(- (lr ** 2) * v_inv_sqrt * d_p - base_c * v_momentum + noise_sample)

                # update theta (Eq 10 left in [1])
                p.add_(v_momentum)

        return loss


