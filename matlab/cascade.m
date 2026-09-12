function out = cascade(H, lambda, maxLev, tgtLev, gamma, adv, shock)
%CASCADE  Forward deleveraging cascade on a network of overlapping portfolios.
%
%   Mirrors src/firebreak/engine.py exactly. Kept in sync by
%   matlab/check_parity.m, which asserts the two agree to 1e-9.
%
%   H       M-by-N holdings, dollars at t0 (prices normalised to 1)
%   lambda  M-by-1 initial gross leverage
%   maxLev  M-by-1 leverage ceiling; above it a fund is forced to sell
%   tgtLev  M-by-1 leverage it deleverages back down to
%   gamma   scalar price-impact coefficient
%   adv     N-by-1 average daily dollar volume
%   shock   N-by-1 returns, e.g. -0.05 for a 5% drop
%
%   Two details that are easy to get wrong and both matter:
%
%   (1) A fund with negative equity has A/E < 0, so a naive "L > maxLev"
%       test is FALSE and the most distressed fund silently stops selling.
%       Insolvency is treated as infinite leverage and full liquidation.
%   (2) Sales settle at the round VWAP, not at book prices. At book prices
%       a fund liquidating its whole book takes zero fire-sale loss, i.e.
%       the funds causing the crash are the only ones immune to it.

    TINY  = 1e-12;
    FLOOR = 1e-6;
    MAXR  = 24;

    [M, N] = size(H);
    units  = H;
    prices = ones(N, 1);
    debt   = (H * prices) .* (1 - 1 ./ lambda);

    equityStart = sum(H * prices - debt);

    prices = prices .* (1 + shock(:));
    equityAfterShock = sum(units * prices - debt);

    defaulted = false(M, 1);
    breached  = false(M, 1);
    rounds    = 0;
    converged = true;

    for step = 1:MAXR
        assets = units * prices;
        equity = assets - debt;

        lev = inf(M, 1);
        solvent = equity > TINY;
        lev(solvent) = assets(solvent) ./ equity(solvent);

        hit = ~defaulted & (sum(units, 2) > TINY) & ...
              (~solvent | lev > maxLev + TINY);
        if ~any(hit), break; end
        if step == MAXR, converged = false; end

        rounds = step;
        breached = breached | hit;

        sold = zeros(M, N);
        wiped = false(M, 1);
        for j = find(hit)'
            if equity(j) <= TINY
                sold(j, :) = units(j, :);      % insolvent: sell everything
                wiped(j) = true;
            elseif assets(j) > TINY
                raise = min(max(assets(j) - tgtLev(j) * equity(j), 0), assets(j));
                sold(j, :) = units(j, :) * (raise / assets(j));
            end
        end

        volume = (sold .* repmat(prices', M, 1));
        volume = sum(volume, 1)';

        before    = prices;
        after     = before .* max(1 - gamma * volume ./ adv(:), FLOOR);
        execution = (before + after) / 2;       % round VWAP

        debt  = debt - sum(sold .* repmat(execution', M, 1), 2);
        units = max(units - sold, 0);
        prices = after;

        defaulted = defaulted | wiped;
    end

    equityEnd = sum(units * prices - debt);
    shockLoss = (equityStart - equityAfterShock) / equityStart;
    finalLoss = (equityStart - equityEnd) / equityStart;

    out = struct( ...
        'shockLoss',     shockLoss, ...
        'finalLoss',     finalLoss, ...
        'amplification', ternary(abs(shockLoss) > TINY, finalLoss / max(shockLoss, TINY), 1.0), ...
        'breaches',      sum(breached), ...
        'defaults',      sum(defaulted), ...
        'rounds',        rounds, ...
        'converged',     converged);
end

function v = ternary(c, a, b)
    if c, v = a; else, v = b; end
end
