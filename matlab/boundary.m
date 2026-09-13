function out = boundary(specFile, outFile, plotFile)
%BOUNDARY  The systemic map, computed in MATLAB and drawn as a surface.
%
%   Sweeps gross leverage against crowding and records how much the system
%   amplifies a fixed single-name shock in each cell. Every cell is a full
%   deleveraging cascade run by cascade.m — 256 of them, nothing interpolated.
%
%   This recomputes what src/firebreak/api.py's _boundary already computes,
%   on purpose. A figure that disagreed with the app's own boundary page would
%   be worse than no figure, so the spec carries Python's grid and this checks
%   against it before drawing. The agreement is the point: two independent
%   implementations of the same cascade, same answer.
%
%   Usage:  boundary('data/cache/boundary_spec.json', ...
%                    'data/cache/boundary_out.json', 'web/boundary-surface.png')

    spec = jsondecode(fileread(specFile));
    H0    = spec.holdings;
    adv   = spec.adv;
    gamma = spec.gamma;
    band  = spec.band;
    levs   = spec.levs(:);
    blends = spec.blends(:);

    shock = zeros(size(H0, 2), 1);
    shock(1) = spec.ref_shock;

    nL = numel(levs); nB = numel(blends);
    grid = zeros(nL, nB);

    clock0 = tic;
    for a = 1:nL
        lev = levs(a);
        M   = size(H0, 1);
        lambda = repmat(lev, M, 1);
        maxLev = repmat(lev * band, M, 1);
        tgt    = repmat(min(max(1.0, lev * 0.95), lev * band), M, 1);
        for b = 1:nB
            Hb = blendTowardMean(H0, blends(b));
            r  = cascade(Hb, lambda, maxLev, tgt, gamma, adv, shock);
            grid(a, b) = r.amplification;
        end
    end
    ms = toc(clock0) * 1000;

    % --- the check that earns the figure -------------------------------------
    worst = NaN;
    if isfield(spec, 'python_grid')
        P = spec.python_grid;
        % Python rounded to 4dp on the way out, so compare at that resolution.
        worst = max(max(abs(round(grid, 4) - P)));
        fprintf('max |MATLAB - Python| over %d cells: %.2e\n', numel(grid), worst);
        if worst > 1e-4
            error('boundary:disagrees', ...
                  ['MATLAB and Python disagree by %.2e — refusing to draw a ' ...
                   'figure that contradicts the app'], worst);
        end
    end

    overlaps = zeros(nB, 1);
    for b = 1:nB
        overlaps(b) = meanOverlap(blendTowardMean(H0, blends(b)));
    end

    % gamma and band travel with the result. Without them the Python side has
    % to guess which configuration this grid describes, or read them out of a
    % spec file that is not committed — and a comparison against the wrong
    % configuration fails for the wrong reason.
    out = struct('grid', grid, 'levs', levs, 'overlaps', overlaps, ...
                 'gamma', gamma, 'band', band, 'ref_shock', spec.ref_shock, ...
                 'cells', numel(grid), 'solve_ms', ms, ...
                 'max_abs_diff_vs_python', worst, 'engine', 'matlab');

    if nargin > 1 && ~isempty(outFile)
        fid = fopen(outFile, 'w');
        closer = onCleanup(@() fclose(fid)); %#ok<NASGU>
        fprintf(fid, '%s', jsonencode(out));
        fprintf('wrote %s  (%d cascades, %.0fms)\n', outFile, numel(grid), ms);
    end

    if nargin > 2 && ~isempty(plotFile)
        try
            drawSurface(overlaps, levs, grid, spec, plotFile);
            fprintf('wrote %s\n', plotFile);
        catch err
            fprintf(2, 'surface not plotted (%s)\n', err.message);
        end
    end
end


function Hm = blendTowardMean(H, blend)
%BLENDTOWARDMEAN  Dial crowding without changing anyone's size.
%   Mirrors api.blend_toward_mean. Each fund keeps its gross assets, so the
%   only thing moving along this axis is how alike the portfolios are.
    totals = sum(H, 2);
    W = zeros(size(H));
    ok = totals > 0;
    W(ok, :) = H(ok, :) ./ totals(ok);

    if blend >= 0
        mu = mean(W, 1);
        mixed = (1 - blend) * W + blend * repmat(mu, size(W, 1), 1);
    else
        % fund j parked entirely in asset j — the genuinely uncrowded end.
        D = zeros(size(W));
        N = size(W, 2);
        for j = 1:size(W, 1)
            D(j, mod(j - 1, N) + 1) = 1;
        end
        mixed = (1 + blend) * W + (-blend) * D;
    end
    Hm = mixed .* totals;
end


function o = meanOverlap(H)
%MEANOVERLAP  Average pairwise cosine similarity of the funds' weight vectors.
    totals = sum(H, 2);
    W = zeros(size(H));
    ok = totals > 0;
    W(ok, :) = H(ok, :) ./ totals(ok);
    n = sqrt(sum(W .^ 2, 2));
    M = size(W, 1);
    acc = [];
    for a = 1:M
        for b = a + 1:M
            d = n(a) * n(b);
            if d > 0
                acc(end + 1) = (W(a, :) * W(b, :)') / d; %#ok<AGROW>
            else
                acc(end + 1) = 0; %#ok<AGROW>
            end
        end
    end
    if isempty(acc), o = 0; else, o = mean(acc); end
end


function drawSurface(overlaps, levs, Z, spec, plotFile)
%DRAWSURFACE  The cliff, as topography.
%
%   The app draws this grid as a heatmap, which is the right thing for reading
%   a value off a cell. A surface is the right thing for seeing that the
%   transition in leverage is a CLIFF and not a ramp — which is the systemic
%   claim, and is hard to feel from colour alone.
    paper = [241 242 238] / 255;
    ink   = [ 20  24  28] / 255;
    mid   = [ 90  96 102] / 255;
    rule  = [198 201 194] / 255;

    % The app's own sequential ramp, interpolated. No viridis: the floor of
    % this surface has to be the same paper the page is printed on.
    stops = [230 231 226; 211 195 184; 192 147 127; ...
             168  80  60; 166  27  20;  74  13   8] / 255;
    cmap = interp1(linspace(0, 1, size(stops, 1)), stops, linspace(0, 1, 256));

    [X, Y] = meshgrid(overlaps, levs);

    f = figure('Visible', 'off', 'Color', paper, ...
               'Units', 'pixels', 'Position', [0 0 1280 860]);
    ax = axes(f);
    s = surf(ax, X, Y, Z, 'EdgeColor', [1 1 1], 'EdgeAlpha', 0.25, ...
             'FaceColor', 'interp');
    colormap(ax, cmap);
    material(ax, 'dull');
    camlight(ax, 'headlight');
    lighting(ax, 'gouraud');
    s.FaceLighting = 'gouraud';

    hold(ax, 'on');

    % The 1.5x threshold, as a plane the surface breaks through, and its
    % contour dropped onto the floor so you can read where it happens.
    zl = [min(Z(:)) max(Z(:)) * 1.02];
    patch(ax, [min(overlaps) max(overlaps) max(overlaps) min(overlaps)], ...
              [min(levs) min(levs) max(levs) max(levs)], ...
              [1.5 1.5 1.5 1.5], ink, 'FaceAlpha', 0.06, 'EdgeColor', 'none');
    contour3(ax, X, Y, Z, [1.5 1.5], 'LineColor', ink, 'LineWidth', 2);
    [~, hc] = contour(ax, X, Y, Z, [1.5 1.5], 'LineColor', ink, 'LineWidth', 1.5);
    hc.ContourZLevel = zl(1);

    % Where the five books actually sit.
    if isfield(spec, 'here')
        hx = spec.here.overlap; hy = spec.here.leverage;
        hz = interp2(X, Y, Z, hx, hy, 'linear');
        if isfinite(hz)
            plot3(ax, [hx hx], [hy hy], [zl(1) hz], '-', 'Color', ink, 'LineWidth', 1.4);
            plot3(ax, hx, hy, hz, 'o', 'MarkerEdgeColor', ink, ...
                  'MarkerFaceColor', paper, 'MarkerSize', 11, 'LineWidth', 1.8);
            text(ax, hx, hy, hz + 0.22, ...
                 sprintf('  the five books as filed — %.2fx', hz), ...
                 'Color', ink, 'FontName', 'Menlo', 'FontSize', 13, ...
                 'FontWeight', 'bold');
        end
    end
    hold(ax, 'off');

    % Short labels: the long ones collided with the tick at the origin, which
    % is where both axis labels land in a default 3-D view.
    xlabel(ax, 'crowding');
    ylabel(ax, 'leverage \lambda');
    zlabel(ax, 'amplification');
    title(ax, sprintf(['%d full cascades — how much the system multiplies a ' ...
                       '%.0f%% single-name shock'], numel(Z), ...
                      abs(spec.ref_shock) * 100), ...
          'FontWeight', 'normal', 'Color', ink);

    set(ax, 'Color', paper, 'XColor', mid, 'YColor', mid, 'ZColor', mid, ...
            'GridColor', rule, 'GridAlpha', 0.6, 'Box', 'off', ...
            'FontName', 'Menlo', 'FontSize', 12, 'TickDir', 'out');
    ax.XRuler.TickLabelGapOffset = 2;
    ax.YRuler.TickLabelGapOffset = 2;
    ax.Title.Color = ink;
    ax.XLabel.Color = mid; ax.YLabel.Color = mid; ax.ZLabel.Color = mid;
    zlim(ax, zl);
    view(ax, -37.5, 26);
    grid(ax, 'on');

    cb = colorbar(ax);
    cb.Color = mid;
    cb.Label.String = 'amplification';
    cb.Label.Color = mid;
    cb.FontName = 'Menlo';

    exportgraphics(f, plotFile, 'Resolution', 144, 'BackgroundColor', paper);
    close(f);
end
