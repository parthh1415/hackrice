function result = stabilise(specFile, outFile, plotFile)
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
%
%   A third argument writes a PNG of the search itself — best-so-far objective
%   and mesh size against cumulative function evaluations. That picture is the
%   argument for being here at all: the flat runs are the objective being
%   piecewise constant, and the mesh halving underneath them is the direct
%   search responding to a failed poll. Omit it and nothing changes; the solve
%   is the product and the plot is a by-product.

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
    trace = zeros(0, 4);   % [cumulative evals, fval, mesh size, start index]

    clock0 = tic;   % handle form, so a tic inside a solver can't reset ours
    for s = 1:size(starts, 1)
        x0 = starts(s, :);
        if strcmp(solver, 'patternsearch')
            try
                [x, fval, exitflag, n, tr] = solvePattern(@cost, @nonlcon, x0, lb, ub);
                if ~isempty(tr)
                    tr(:, 1) = tr(:, 1) + evals;          % continue the x axis
                    trace = [trace; tr, repmat(s, size(tr, 1), 1)]; %#ok<AGROW>
                end
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

    % The picture of the search. Wrapped so a plotting failure — a headless
    % box with no graphics, an export that cannot write — never costs us the
    % solve. The answer is the product; this is a by-product.
    if nargin > 1
        if nargin < 3 || isempty(plotFile)
            [d, ~, ~] = fileparts(outFile);
            plotFile = fullfile(d, 'solve_trace.png');
        end
        try
            drawTrace(trace, plotFile, solver, evals);
            fprintf('wrote %s\n', plotFile);
        catch plotErr
            fprintf(2, 'trace not plotted (%s)\n', plotErr.message);
        end
    end

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

function [x, fval, exitflag, n, trace] = solvePattern(fun, nlc, x0, lb, ub)
%SOLVEPATTERN  patternsearch on the mixed (fund, asset, reduction) problem.
%
%   MeshTolerance is 1e-6 rather than 1e-3 because the reduction is the one
%   variable worth refining: at 1e-3 the answer stops a factor of 2.7 short
%   of the cheapest fix, and the extra polls are free at this problem size.
    rows = zeros(0, 3);
    opts = optimoptions('patternsearch', ...
        'Display', 'off', 'UseCompletePoll', true, ...
        'MeshTolerance', 1e-6, 'MaxIterations', 400, ...
        'OutputFcn', @record);
    [x, fval, exitflag, output] = patternsearch(fun, x0, [], [], [], [], lb, ub, nlc, opts);
    n = output.funccount;   % lowercase: Global Optimization Toolbox spelling
    trace = rows;

    function [stop, options, changed] = record(optimvalues, options, flag)
    %RECORD  One row per iteration. Reports only; never steers the search.
        stop = false; changed = false;
        if strcmp(flag, 'interrupt')
            return
        end
        mesh = NaN;
        if isfield(optimvalues, 'meshsize'), mesh = optimvalues.meshsize; end
        rows(end+1, :) = [optimvalues.funccount, optimvalues.fval, mesh]; %#ok<AGROW>
    end
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

function drawTrace(trace, plotFile, solver, evals)
%DRAWTRACE  The search, as a picture.
%
%   Top: the best objective found so far, against cumulative function
%   evaluations. It is a staircase because a direct search only moves when a
%   poll succeeds, and the flat runs between steps are the objective being
%   piecewise constant across breach events — which is the whole reason this
%   solve is not a gradient method.
%
%   Bottom: the mesh size. Every halving is a failed poll: the search found
%   nothing better at the current spacing and tightened it. The two panels read
%   together — the mesh collapses exactly where the objective stops moving.
%
%   Captions sit in FIGURE space rather than data space. A label placed in data
%   coordinates on a log axis moves when the data does, and this figure is
%   regenerated on every solve.
    if isempty(trace)
        error('stabilise:noTrace', 'no iterations were recorded');
    end

    paper = [241 242 238] / 255;   % --paper-raised
    ink   = [ 20  24  28] / 255;   % --ink
    mid   = [ 90  96 102] / 255;   % --ink-mid
    rule  = [198 201 194] / 255;   % --rule
    faint = [141 146 153] / 255;   % --ink-faint

    x     = trace(:, 1);
    fval  = trace(:, 2);
    mesh  = trace(:, 3);
    start = trace(:, 4);

    % Infeasible polls come back as Inf, which a log axis cannot draw and which
    % is not a cost anyone paid. Drop them from the objective series only.
    ok   = isfinite(fval) & fval > 0;
    xo   = x(ok);
    bestSoFar = cummin(fval(ok));
    final = bestSoFar(end);
    % the first evaluation at which the answer stopped improving
    settledAt = xo(find(bestSoFar <= final * (1 + 1e-12), 1, 'first'));

    f = figure('Visible', 'off', 'Color', paper, ...
               'Units', 'pixels', 'Position', [0 0 1500 820]);
    tl = tiledlayout(f, 2, 1, 'TileSpacing', 'compact', 'Padding', 'loose');

    ax1 = nexttile(tl);
    hold(ax1, 'on');
    % everything after the answer was found, shaded: the search proving to
    % itself that nothing cheaper exists.
    yl1 = [min(bestSoFar) * 0.6, max(bestSoFar) * 1.6];
    patch(ax1, [settledAt max(x) max(x) settledAt], ...
               [yl1(1) yl1(1) yl1(2) yl1(2)], ink, ...
               'FaceAlpha', 0.045, 'EdgeColor', 'none');
    stairs(ax1, xo, bestSoFar, 'Color', ink, 'LineWidth', 1.8);
    plot(ax1, settledAt, final, 'o', 'MarkerEdgeColor', ink, ...
         'MarkerFaceColor', paper, 'MarkerSize', 9, 'LineWidth', 1.8);
    hold(ax1, 'off');
    set(ax1, 'YScale', 'log');
    ylim(ax1, yl1);
    ylabel(ax1, 'best cost so far');

    ax2 = nexttile(tl);
    if any(isfinite(mesh))
        stairs(ax2, x, mesh, 'Color', ink, 'LineWidth', 1.8);
        set(ax2, 'YScale', 'log');
    end
    ylabel(ax2, 'mesh size');
    xlabel(ax2, 'cumulative function evaluations — each one a full cascade');

    % Where one multi-start run ends and the next begins. Faint ink, not red:
    % §1 of DESIGN.md gives the one colour exactly one meaning, a limit being
    % crossed, and a restart is not one.
    edges = x(find(diff(start) ~= 0) + 1);
    for ax = [ax1 ax2]
        hold(ax, 'on');
        yl = ylim(ax);
        for k = 1:numel(edges)
            plot(ax, [edges(k) edges(k)], yl, ':', 'Color', faint, 'LineWidth', 1);
        end
        ylim(ax, yl);
        hold(ax, 'off');
        set(ax, 'Color', paper, 'XColor', mid, 'YColor', mid, ...
                'GridColor', rule, 'GridAlpha', 0.55, 'Box', 'off', ...
                'MinorGridLineStyle', 'none', ...
                'FontName', 'Menlo', 'FontSize', 13, 'TickDir', 'out');
        grid(ax, 'on');
        ax.YLabel.Color = mid;
        ax.XLabel.Color = mid;
    end
    linkaxes([ax1 ax2], 'x');
    xlim(ax1, [0 max(x)]);

    title(tl, sprintf('How %s found it', solver), ...
          'FontName', 'Menlo', 'FontSize', 17, 'FontWeight', 'bold', ...
          'Color', ink);
    subtitle(tl, sprintf(['%d evaluations, %d restarts — the answer was found ' ...
                          'by evaluation %d and the rest is proof'], ...
                         evals, numel(edges), round(settledAt)), ...
             'FontName', 'Menlo', 'FontSize', 13, 'Color', mid);

    annotation(f, 'textbox', [0.62 0.605 0.30 0.05], ...
        'String', sprintf('settled at %.3e', final), ...
        'Color', mid, 'FontName', 'Menlo', 'FontSize', 13, ...
        'EdgeColor', 'none', 'HorizontalAlignment', 'center');
    annotation(f, 'textbox', [0.43 0.145 0.38 0.04], ...
        'String', 'each drop is a failed poll tightening the mesh', ...
        'Color', mid, 'FontName', 'Menlo', 'FontSize', 13, ...
        'EdgeColor', 'none', 'HorizontalAlignment', 'center');

    exportgraphics(f, plotFile, 'Resolution', 144, 'BackgroundColor', paper);
    close(f);
end
