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

    H = spec.holdings;
    if iscell(H) || ~isnumeric(H) || ~ismatrix(H)
        % jsondecode hands back a cell array when the rows are ragged, and
        % the first complaint would otherwise come from sum() further down
        error('stabilise:badHoldings', ...
              'spec.holdings must decode to a rectangular numeric matrix');
    end
    lambda  = spec.leverage(:);
    maxLev  = spec.max_leverage(:);
    tgtLev  = spec.target_leverage(:);
    gamma   = spec.gamma;
    adv     = spec.adv(:);
    shock   = spec.shock(:);
    nBreach = spec.breaches;

    [M, N] = size(H);
    total  = sum(H(:));

    % survives(x) == true when the patched system stays under the failure
    % condition. x is (fund, asset, reduction) with the first two relaxed to
    % continuous and rounded inside — patternsearch handles mixed domains
    % badly otherwise.
    %
    % The locals below are deliberately not named j/i/r. Those three are
    % assigned in the parent after the solve, and a nested function that
    % shares a name with its parent shares the variable itself, so every
    % probe would be scribbling on the answer we are about to report.
    function c = violation(x)
        [fundIdx, assetIdx, red] = unpack(x, M, N);
        P = H;
        P(fundIdx, assetIdx) = P(fundIdx, assetIdx) * (1 - red);
        sim = cascade(P, lambda, maxLev, tgtLev, gamma, adv, shock);
        % positive when still failing; the optimiser drives this to <= 0
        c = sim.breaches - (nBreach - 1);
    end

    function f = cost(x)
        [fundIdx, assetIdx, red] = unpack(x, M, N);
        f = H(fundIdx, assetIdx) * red / total;
    end

    function [c, ceq] = nonlcon(x)
        c = violation(x);
        ceq = [];
    end

    lb = [1, 1, 0];
    ub = [M, N, 1];

    % patternsearch halves its mesh on a failed poll, and once the mesh is
    % under 0.5 neither round(x(1)) nor round(x(2)) can move again — the
    % discrete half of the search is finished while the mesh is still coarse.
    % From the lone x0 = [1 1 0.25] this file used to use, a problem whose
    % answer sits away from (1,1) came back 14.7x more expensive than the
    % optimum. A coarse grid of starts costs a few thousand cascades, which
    % on a book this size is milliseconds, and recovers it.
    starts = startGrid(M, N);

    % Decide upfront where we can, so the common "toolbox simply isn't
    % installed" case never has to be inferred from error text.
    if exist('patternsearch', 'file')
        solver = 'patternsearch';
    elseif exist('fmincon', 'file')
        solver = 'fmincon';
    else
        error('stabilise:noSolver', ...
              ['needs patternsearch (Global Optimization Toolbox) or fmincon ' ...
               '(Optimization Toolbox); neither is on the path']);
    end
    evals = 0;
    best  = [];

    clock0 = tic;   % handle form, so a tic inside a solver can't reset ours
    for s = 1:size(starts, 1)
        x0 = starts(s, :);
        if strcmp(solver, 'patternsearch')
            try
                [x, fval, exitflag, n] = solvePattern(@cost, @nonlcon, x0, lb, ub);
            catch err
                % Global Optimization Toolbox absent or unlicensed. fmincon
                % is Optimization Toolbox, not base MATLAB — but GOT depends
                % on Optimization Toolbox, so anyone who could have run
                % patternsearch can certainly run fmincon.
                %
                % Only a missing solver earns the fallback. A bare catch here
                % would turn any bug inside cascade — or a misspelt output
                % field — into a silent re-solve reported under the wrong
                % solver name, which is the one failure this file must not have.
                if ~isMissingSolver(err) || ~exist('fmincon', 'file')
                    rethrow(err);
                end
                solver = 'fmincon';
                [x, fval, exitflag, n] = solveFmincon(@cost, @nonlcon, x0, lb, ub);
            end
        else
            [x, fval, exitflag, n] = solveFmincon(@cost, @nonlcon, x0, lb, ub);
        end
        evals = evals + n;

        % Either solver can exit on an infeasible point and still hand back an
        % x, so feasibility is checked here rather than taken on trust. Cost
        % first: && short-circuits, and a start that cannot beat what we
        % already have is not worth another cascade to disqualify.
        if (isempty(best) || fval < best.fval) && violation(x) <= 0
            best = struct('x', x, 'fval', fval, 'exitflag', exitflag);
        end
    end
    ms = toc(clock0) * 1000;

    if isempty(best)
        error('stabilise:noFeasibleFix', ...
              'no single-position reduction clears the failure condition');
    end

    [j, i, r] = unpack(best.x, M, N);

    % Echo the spec's fingerprint back. Without it the bridge can only fall
    % back to comparing file mtimes to decide whether this result still answers
    % the question on screen — which works, but an exact match is better and
    % this is the one line that provides it.
    if isfield(spec, 'fingerprint')
        fingerprint = spec.fingerprint;
    else
        fingerprint = '';
    end

    result = struct( ...
        'fingerprint', fingerprint, ...
        'fund_index',  j - 1, ...        % python is 0-indexed
        'asset_index', i - 1, ...
        'reduction',   r, ...
        'cost',        best.fval, ...
        'solver',      solver, ...
        'evaluations', evals, ...
        'exit_flag',   best.exitflag, ...
        'solve_ms',    ms, ...
        'engine',      'matlab');

    if nargin > 1
        fid = fopen(outFile, 'w');
        if fid < 0
            error('stabilise:cannotWrite', 'could not open %s for writing', outFile);
        end
        % held only for its destructor, which closes the file on any exit path
        closer = onCleanup(@() fclose(fid)); %#ok<NASGU>
        fprintf(fid, '%s', jsonencode(result));
        fprintf('wrote %s  (%s, %d evals, %.0fms)\n', outFile, solver, evals, ms);
    end
end

function [x, fval, exitflag, n] = solvePattern(fun, nlc, x0, lb, ub)
%SOLVEPATTERN  patternsearch on the mixed (fund, asset, reduction) problem.
%
%   MeshTolerance is 1e-6 rather than 1e-3 because the reduction is the one
%   variable worth refining: at 1e-3 the answer stops a factor of 2.7 short
%   of the cheapest fix, and the extra polls are free at this problem size.
    opts = optimoptions('patternsearch', ...
        'Display', 'off', 'UseCompletePoll', true, ...
        'MeshTolerance', 1e-6, 'MaxIterations', 400);
    [x, fval, exitflag, output] = patternsearch(fun, x0, [], [], [], [], lb, ub, nlc, opts);
    n = output.funccount;   % lowercase: Global Optimization Toolbox spelling
end

function [x, fval, exitflag, n] = solveFmincon(fun, nlc, x0, lb, ub)
%SOLVEFMINCON  Fallback for a machine without the Global Optimization Toolbox.
%
%   Worse suited to this problem — the objective is piecewise constant in two
%   of its three variables — but it is better than refusing to solve.
    opts = optimoptions('fmincon', 'Display', 'off', 'Algorithm', 'sqp');
    [x, fval, exitflag, output] = fmincon(fun, x0, [], [], [], [], lb, ub, nlc, opts);
    n = output.funcCount;   % camelCase: Optimization Toolbox spells it differently
end

function tf = isMissingSolver(err)
%ISMISSINGSOLVER  Is this "the toolbox isn't here", or a real bug?
%
%   A missing toolbox arrives by several routes — undefined function, a
%   licence checkout that failed, or optimoptions refusing a solver name it
%   doesn't recognise — and they do not share an identifier. A cascade bug
%   ("Matrix dimensions must agree", or our own cascade:targetOutOfRange)
%   matches none of these, which is the distinction that matters.
    text = lower([err.identifier ' ' err.message]);
    tf = strcmp(err.identifier, 'MATLAB:UndefinedFunction') || ...
         any(contains(text, {'license', 'licence', 'toolbox', ...
                             'not a valid solver', 'undefined function'}));
end

function starts = startGrid(M, N)
%STARTGRID  Spread of x0 points so the discrete dims are actually explored.
%
%   Three positions per dimension is enough: the mesh only needs to reach the
%   right fund and asset, and from any start within a couple of integer steps
%   it does. Duplicates are dropped so a 1- or 2-fund book stays cheap.
    funds  = unique(round(linspace(1, M, min(M, 3))));
    assets = unique(round(linspace(1, N, min(N, 3))));
    [F, A] = ndgrid(funds, assets);
    starts = [F(:), A(:), repmat(0.25, numel(F), 1)];
end

function [fundIdx, assetIdx, red] = unpack(x, M, N)
%UNPACK  Continuous x -> the discrete (fund, asset, reduction) it stands for.
%
%   NaN is rejected explicitly: two-argument min/max omit NaN, so
%   min(max(round(NaN),1),M) is 1 and a solver that fell over would otherwise
%   hand back a plausible-looking "fund 1, asset 1, reduce by 0" that nobody
%   downstream could tell from a real answer.
    if any(~isfinite(x(1:3)))
        error('stabilise:nonFiniteX', 'solver returned a non-finite point');
    end
    fundIdx  = min(max(round(x(1)), 1), M);
    assetIdx = min(max(round(x(2)), 1), N);
    red      = min(max(x(3), 0), 1);
end
