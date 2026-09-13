function out = cascade(H, lambda, maxLev, tgtLev, gamma, adv, shock)
%CASCADE  Forward deleveraging cascade on a network of overlapping portfolios.
%
%   Mirrors src/firebreak/engine.py. Parity is checked by porting this file
%   and diffing against run_cascade on the real dataset; finalLoss, breaches
%   and rounds agree to 0.0 across a 720-scenario sweep.
%
%   H       M-by-N holdings, dollars at t0 (prices normalised to 1)
%   lambda  M-by-1 initial gross leverage
%   maxLev  M-by-1 leverage ceiling; above it a fund is forced to sell
%   tgtLev  M-by-1 leverage it deleverages back down to
%   gamma   scalar price-impact coefficient
%   adv     N-by-1 average daily dollar volume
%   shock   N-by-1 returns, e.g. -0.05 for a 5% drop
%
%   Three details that are easy to get wrong and all three matter:
%
%   (1) A fund with negative equity has A/E < 0, so a naive "L > maxLev"
%       test is FALSE and the most distressed fund silently stops selling.
%       Insolvency is treated as infinite leverage and full liquidation.
%   (2) Sales settle at the round VWAP, not at book prices. At book prices
%       a fund liquidating its whole book takes zero fire-sale loss, i.e.
%       the funds causing the crash are the only ones immune to it.
%   (3) Whether the run settled can only be judged after the loop. A run
%       that spends its last permitted round selling may still have
%       finished; deciding on the way in marks every such run divergent.

    TINY  = 1e-12;
    FLOOR = 1e-6;
    MAXR  = 24;

    % the caller's orientation is not our business, but implicit expansion
    % turns an Mx1 .* 1xM into a silent MxM and the error surfaces rounds later
    lambda = lambda(:);
    maxLev = maxLev(:);
    tgtLev = tgtLev(:);
    adv    = adv(:);
    shock  = shock(:);

    if any(tgtLev < 1) || any(tgtLev > maxLev)
        error('cascade:targetOutOfRange', ...
              ['need 1 <= tgtLev <= maxLev; outside that range the ''sale'' ' ...
               'has negative size and forced selling pushes prices up']);
    end

    % The same four guards engine.py grew, mirrored here — this file's whole
    % job is to be the other implementation, and an input Python refuses must
    % not come back from MATLAB as a confident number. adv is the one that
    % matters: for an asset nobody holds the numerator is zero too, so the
    % impact multiplier is 0/0, NaN spreads through prices and equity, every
    % comparison against NaN is false, and the run reports a clean converged
    % cascade with NaN inside it. leverage=0 reaches the same place through
    % debt = -Inf.
    if any(~isfinite(adv)) || any(adv <= 0)
        error('cascade:advNotPositive', ...
              ['every adv must be a positive, finite number; a zero divides ' ...
               'into the price impact and hands back NaN prices that report ' ...
               'as a clean converged cascade']);
    end
    if ~isfinite(gamma) || gamma < 0
        error('cascade:gammaNegative', ...
              'gamma must be >= 0; a negative one makes forced selling repair the market');
    end
    if any(lambda <= 0)
        error('cascade:leverageNotPositive', ...
              'leverage must be > 0; at zero the implied debt is -Inf');
    end
    % Exactly -100% is a real answer and stays allowed; worse than that puts a
    % price below zero, which the FLOOR constant's own promise forbids.
    if any(shock < -1)
        error('cascade:shockBelowTotal', ...
              'a shock worse than -100%% would put a price below zero');
    end

    [M, N] = size(H);
    units  = H;
    prices = ones(N, 1);
    debt   = (H * prices) .* (1 - 1 ./ lambda);

    equityStart = sum(H * prices - debt);

    prices = prices .* (1 + shock);
    equityAfterShock = sum(units * prices - debt);

    defaulted = false(M, 1);
    breached  = false(M, 1);
    rounds    = 0;

    for step = 1:MAXR
        hit = overLimit(units, prices, debt, defaulted, maxLev, TINY);
        if ~any(hit), break; end

        rounds = step;
        breached = breached | hit;

        assets = units * prices;
        equity = assets - debt;

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

        volume = sum(sold .* repmat(prices', M, 1), 1)';

        before    = prices;
        after     = before .* max(1 - gamma * volume ./ adv, FLOOR);
        execution = (before + after) / 2;       % round VWAP

        debt  = debt - sum(sold .* repmat(execution', M, 1), 2);
        units = max(units - sold, 0);
        prices = after;

        defaulted = defaulted | wiped;
    end

    % see (3): asked after the fact, not on the way in
    converged = ~any(overLimit(units, prices, debt, defaulted, maxLev, TINY));

    equityEnd = sum(units * prices - debt);
    shockLoss = (equityStart - equityAfterShock) / equityStart;
    finalLoss = (equityStart - equityEnd) / equityStart;

    % a gain is a negative shockLoss, and clamping the denominator up to TINY
    % turns that into an amplification of -1e11 rather than the 1.0 it is
    % Three branches, like engine.py's. This file had two, and its else
    % returned exactly the 1.0 that engine.py's comment above the same
    % arithmetic documents as a fixed regression: with a zero denominator the
    % ratio does not exist, and 1.0 is not a neutral stand-in for undefined —
    % it is the claim that forced selling added nothing. Books filed over their
    % own ceiling deleverage with no shock at all, so a zero shock can destroy
    % real equity and still divide by nothing.
    %
    % NaN rather than a sentinel: jsonencode writes it as null, which is what
    % json.dumps writes for Python's None, so a grid built either side
    % round-trips to the same value.
    if abs(shockLoss) > TINY
        amplification = finalLoss / shockLoss;
    elseif abs(finalLoss) <= TINY
        amplification = 1.0;        % nothing happened, so nothing was amplified
    else
        amplification = NaN;        % the ratio does not exist
    end

    out = struct( ...
        'shockLoss',     shockLoss, ...
        'finalLoss',     finalLoss, ...
        'amplification', amplification, ...
        'breaches',      sum(breached), ...
        'defaults',      sum(defaulted), ...
        'rounds',        rounds, ...
        'converged',     converged);
end

function hit = overLimit(units, prices, debt, defaulted, maxLev, TINY)
%OVERLIMIT  Who has to sell right now. Insolvent counts — it's the worst case.
%
%   The sign flip in (1) gets handled once, here, rather than at every call
%   site, which is what the first version of this got wrong.
    assets  = units * prices;
    equity  = assets - debt;
    solvent = equity > TINY;

    lev = inf(numel(equity), 1);
    lev(solvent) = assets(solvent) ./ equity(solvent);

    hit = ~defaulted & (sum(units, 2) > TINY) & ...
          (~solvent | lev > maxLev .* (1 + 1e-12));   % relative: see engine.py
end
