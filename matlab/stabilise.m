function result = stabilise(specFile, outFile)
%STABILISE  Minimum-cost intervention that survives a given shock.
%
%   This is the part of Firebreak that genuinely needs MATLAB. The
%   objective is a *simulation* — you cannot differentiate it, the feasible
%   set is defined by whether a cascade crosses a discrete failure
%   condition, and breach events make the landscape piecewise constant.
%   That is exactly the problem class patternsearch is built for, and
%   exactly where gradient methods fall over.
%
%   Reads a JSON spec written by Python, writes a JSON result back. A file
%   bridge rather than the Engine API on purpose: it works from MATLAB
%   Online with no local install, which is how most hackathon teams
%   actually have MATLAB.
%
%   Usage:  stabilise('data/cache/solve_spec.json', 'data/cache/solve_out.json')

    spec = jsondecode(fileread(specFile));

    H      = spec.holdings;
    lambda = spec.leverage(:);
    maxLev = spec.max_leverage(:);
    tgtLev = spec.target_leverage(:);
    gamma  = spec.gamma;
    adv    = spec.adv(:);
    shock  = spec.shock(:);
    nBreach = spec.breaches;

    [M, N] = size(H);
    total  = sum(H(:));

    % survives(x) == true when the patched system stays under the failure
    % condition. x is (fund, asset, reduction) with the first two relaxed to
    % continuous and rounded inside — patternsearch handles mixed domains
    % badly otherwise.
    function c = violation(x)
        j = min(max(round(x(1)), 1), M);
        i = min(max(round(x(2)), 1), N);
        r = min(max(x(3), 0), 1);
        P = H;
        P(j, i) = P(j, i) * (1 - r);
        out = cascade(P, lambda, maxLev, tgtLev, gamma, adv, shock);
        % positive when still failing; the optimiser drives this to <= 0
        c = out.breaches - (nBreach - 1);
    end

    function f = cost(x)
        j = min(max(round(x(1)), 1), M);
        i = min(max(round(x(2)), 1), N);
        r = min(max(x(3), 0), 1);
        f = H(j, i) * r / total;
    end

    lb = [1, 1, 0];
    ub = [M, N, 1];
    x0 = [1, 1, 0.25];

    solver = 'patternsearch';
    tic;
    try
        opts = optimoptions('patternsearch', ...
            'Display', 'off', 'UseCompletePoll', true, ...
            'MeshTolerance', 1e-3, 'MaxIterations', 400);
        [x, fval, exitflag, output] = patternsearch( ...
            @cost, x0, [], [], [], [], lb, ub, @nonlcon, opts);
        evals = output.funccount;
    catch
        % Global Optimization Toolbox absent — fmincon is in base MATLAB
        solver = 'fmincon';
        opts = optimoptions('fmincon', 'Display', 'off', 'Algorithm', 'sqp');
        [x, fval, exitflag, output] = fmincon( ...
            @cost, x0, [], [], [], [], lb, ub, @nonlcon, opts);
        evals = output.funcCount;
    end
    ms = toc * 1000;

    function [c, ceq] = nonlcon(x)
        c = violation(x);
        ceq = [];
    end

    j = min(max(round(x(1)), 1), M);
    i = min(max(round(x(2)), 1), N);
    r = min(max(x(3), 0), 1);

    result = struct( ...
        'fund_index',  j - 1, ...        % python is 0-indexed
        'asset_index', i - 1, ...
        'reduction',   r, ...
        'cost',        fval, ...
        'solver',      solver, ...
        'evaluations', evals, ...
        'exit_flag',   exitflag, ...
        'solve_ms',    ms, ...
        'engine',      'matlab');

    if nargin > 1
        fid = fopen(outFile, 'w');
        fwrite(fid, jsonencode(result));
        fclose(fid);
        fprintf('wrote %s  (%s, %d evals, %.0fms)\n', outFile, solver, evals, ms);
    end
end
