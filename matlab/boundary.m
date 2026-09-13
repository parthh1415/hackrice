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
        % MATLAB's max OMITS NaN, so a cell that is not comparable at all
        % would score as perfect agreement and stamp max_abs_diff 0 on the
        % figure. cascade.m can now return NaN deliberately — an amplification
        % whose denominator is zero — so this has to look before it maxes.
        diffs = abs(round(grid, 4) - P);
        if any(~isfinite(diffs(:)))
            bad = sum(~isfinite(diffs(:)));
            error('boundary:incomparable', ...
                  ['%d of %d cells are not comparable (NaN or Inf in the ' ...
                   'difference) — refusing to claim agreement on a grid with ' ...
                   'holes in it'], bad, numel(diffs));
        end
        worst = max(max(diffs));
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
                 'asset_count', size(H0, 2), 'cells', numel(grid), 'solve_ms', ms, ...
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
%   The app draws this grid as a heatmap, which is the right tool for reading a
%   value off a cell. A surface is the right tool for seeing that the
%   transition in leverage is a CLIFF and not a ramp — which is the systemic
%   claim, and is hard to feel from colour alone.
%
%   Composition notes, because the first version was muddy: no mesh lines (they
%   washed the form out at this grid density), two lights rather than a
%   headlight (a headlight flattens exactly the feature the figure exists to
%   show), no colorbar (the z axis already carries amplification), and the
%   plain and the plateau are labelled on the surface itself so the picture
%   states its own conclusion.
    paper = paletteOf(spec, 'paper_raised', [241 242 238] / 255);
    ink   = paletteOf(spec, 'ink',          [ 20  24  28] / 255);
    mid   = paletteOf(spec, 'ink_mid',      [ 90  96 102] / 255);
    rule  = paletteOf(spec, 'rule',         [198 201 194] / 255);

    % The app's own sequential ramp, interpolated. No viridis: the floor of
    % this surface has to be the same paper the page is printed on.
    stops = [paletteOf(spec, 'ramp_0', [230 231 226] / 255);
             paletteOf(spec, 'ramp_1', [211 195 184] / 255);
             paletteOf(spec, 'ramp_2', [192 147 127] / 255);
             paletteOf(spec, 'ramp_3', [168  80  60] / 255);
             paletteOf(spec, 'ramp_4', [166  27  20] / 255);
             paletteOf(spec, 'ramp_5', [ 74  13   8] / 255)];
    cmap = interp1(linspace(0, 1, size(stops, 1)), stops, linspace(0, 1, 256));

    [X, Y] = meshgrid(overlaps, levs);
    zFloor = 1.0;
    zTop   = max(Z(:)) * 1.06;

    f = figure('Visible', 'off', 'Color', paper, ...
               'Units', 'pixels', 'Position', [0 0 1500 1000]);
    ax = axes(f, 'Position', [0.07 0.09 0.86 0.83]);

    % The shadow of the amplifying region, dropped on the floor. It reads as
    % the map the page already shows, underneath its own topography.
    hold(ax, 'on');
    shadow = double(Z >= 1.5);
    contourf(ax, X, Y, shadow, [0.5 0.5], 'LineStyle', 'none', ...
             'FaceColor', min(1, max(0, paper + (ink - paper) * 0.10)));
    hc = get(ax, 'Children');
    for k = 1:numel(hc)
        if isprop(hc(k), 'ContourZLevel'), hc(k).ContourZLevel = zFloor; end
    end

    s = surf(ax, X, Y, Z, 'EdgeColor', 'none', 'FaceColor', 'interp', ...
             'FaceAlpha', 1.0);
    colormap(ax, cmap);
    s.FaceLighting    = 'gouraud';
    s.AmbientStrength = 0.62;
    s.DiffuseStrength = 0.52;
    s.SpecularStrength = 0.08;
    % Two lights. One headlight flattens the cliff, which is the one feature
    % this figure exists to show.
    light(ax, 'Position', [-1.2  0.2  2.0], 'Style', 'infinite');
    light(ax, 'Position', [ 0.9 -1.4  0.6], 'Style', 'infinite');

    % The 1.5x threshold where it crosses the surface.
    contour3(ax, X, Y, Z, [1.5 1.5], 'LineColor', ink, 'LineWidth', 2.4);

    % Where the five books actually sit, with a stem to the floor.
    if isfield(spec, 'here')
        hx = spec.here.overlap; hy = spec.here.leverage;
        hz = interp2(X, Y, Z, hx, hy, 'linear');
        if isfinite(hz)
            plot3(ax, [hx hx], [hy hy], [zFloor hz], '-', 'Color', ink, 'LineWidth', 1.6);
            plot3(ax, hx, hy, hz, 'o', 'MarkerEdgeColor', ink, ...
                  'MarkerFaceColor', paper, 'MarkerSize', 13, 'LineWidth', 2.2);
            text(ax, hx, hy, zTop, ...
                 sprintf('the five books as filed\n\\lambda %.1f, overlap %.2f — %.2fx', ...
                         hy, hx, hz), ...
                 'Color', ink, 'FontName', 'Menlo', 'FontSize', 14, ...
                 'FontWeight', 'bold', 'HorizontalAlignment', 'center', ...
                 'VerticalAlignment', 'bottom');
            plot3(ax, [hx hx], [hy hy], [hz zTop], ':', 'Color', ink, 'LineWidth', 1);
        end
    end

    % The picture states its own conclusion. Both labels are placed against the
    % SURFACE rather than against the axis box: the first version put one off
    % the right edge and buried the other inside the surface, because text at
    % exactly z = max(Z) is coplanar with the thing drawn on top of it.
    % These two are placed in FIGURE space, not data space, and deliberately.
    % text() in a 3-D axes is depth-sorted against the surface, so a label in
    % data coordinates is either in front of the geometry or behind it
    % depending on the camera — three attempts produced, in turn, a label
    % buried to its waist in a ridge, one missing its first two letters, and
    % one that vanished completely. An annotation floats above the axes and
    % cannot be occluded, which is the correct behaviour for a caption.
    annotation(f, 'textbox', [0.22 0.60 0.26 0.06], 'String', 'amplifying', ...
        'Color', paper, 'FontName', 'Menlo', 'FontSize', 19, ...
        'FontWeight', 'bold', 'EdgeColor', 'none', ...
        'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle');
    annotation(f, 'textbox', [0.39 0.175 0.34 0.05], ...
        'String', 'absorbed — every shock dies out here', ...
        'Color', mid, 'FontName', 'Menlo', 'FontSize', 14, ...
        'EdgeColor', 'none', 'HorizontalAlignment', 'center', ...
        'VerticalAlignment', 'middle');
    hold(ax, 'off');

    xlabel(ax, 'crowding');
    ylabel(ax, 'leverage \lambda');
    zlabel(ax, 'amplification');
    title(ax, sprintf(['Where the system stops absorbing\n' ...
                       '\\rm\\fontsize{13}%d full cascades, one per cell — ' ...
                       'a %.0f%% single-name shock at every point'], ...
                      numel(Z), abs(spec.ref_shock) * 100), ...
          'FontWeight', 'bold', 'Color', ink, 'FontSize', 17);

    set(ax, 'Color', paper, 'XColor', mid, 'YColor', mid, 'ZColor', mid, ...
            'GridColor', rule, 'GridAlpha', 0.75, 'Box', 'off', ...
            'FontName', 'Menlo', 'FontSize', 13, 'TickDir', 'out', ...
            'Projection', 'perspective');
    ax.Title.Color = ink;
    ax.XLabel.Color = mid; ax.YLabel.Color = mid; ax.ZLabel.Color = mid;
    ax.XRuler.TickLabelGapOffset = 2;
    ax.YRuler.TickLabelGapOffset = 2;
    zlim(ax, [zFloor zTop]);
    xlim(ax, [min(overlaps) max(overlaps)]);
    ylim(ax, [min(levs) max(levs)]);
    % Chosen by rendering the alternatives and looking: this one shows the
    % plateau, the cliff and the plain in one frame with none of the three
    % hiding the others.
    view(ax, -25, 34);
    grid(ax, 'on');

    exportgraphics(f, plotFile, 'Resolution', 144, 'BackgroundColor', paper);
    close(f);
end


function c = paletteOf(spec, name, fallback)
%PALETTEOF  One colour from the app's palette, or the built-in fallback.
%
%   The spec carries web/tokens.css's values so a figure exported here is in
%   whatever the product is currently wearing — recolour the app and these
%   follow. The fallback is what this file used when it was written; it keeps
%   the figure legible if the spec is old or the palette could not be read,
%   which should cost a nice colour and never the solve.
    c = fallback;
    if isfield(spec, 'palette') && isfield(spec.palette, name)
        v = spec.palette.(name);
        if numel(v) == 3
            c = reshape(double(v), 1, 3);
        end
    end
end
