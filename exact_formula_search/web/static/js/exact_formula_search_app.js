(function () {
  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const Glass = window.LiquidGlassEngine.Glass;
  const GlassMaterial = window.LiquidGlassEngine.GlassMaterial;
  const GlassSwitch = window.LiquidGlassEngine.GlassSwitch;
  const GlassSlider = window.LiquidGlassEngine.GlassSlider;
  const glassValue = window.LiquidGlassEngine.glassValue;
  const animateGlassValue = window.LiquidGlassEngine.animateGlassValue;
  const {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState
  } = React;
  const h = React.createElement;
  const HISTORY_KEY = "exact_formula_history_v1";
  const HISTORY_LIMIT = 12;
  const STREAM_ENDPOINT = "/api/search/stream";
  const FORMALIZE_ENDPOINT = "/api/formalize";
  const PRESETS_ENDPOINT = "/api/presets";
  const HEALTH_ENDPOINT = "/api/health";
  const PIPELINE_STEPS = [{
    id: "formalize",
    label: "Formalize",
    events: ["search_started", "formalization"]
  }, {
    id: "queue",
    label: "Queue frontiers",
    events: ["frontier_queued"]
  }, {
    id: "generate",
    label: "Generate worker",
    events: ["code_generated"]
  }, {
    id: "execute",
    label: "Execute",
    events: ["frontier_visit", "execution_completed"]
  }, {
    id: "verify",
    label: "Verify",
    events: ["verification_completed"]
  }, {
    id: "critique",
    label: "Critique",
    events: ["critique_completed"]
  }, {
    id: "repair",
    label: "Repair",
    events: ["repair_triggered"]
  }, {
    id: "certify",
    label: "Certify",
    events: ["search_completed", "search_exhausted", "symbolic_proof"]
  }];
  const EVENT_META = {
    search_started: {
      tone: "info",
      label: "search started"
    },
    formalization: {
      tone: "info",
      label: "formalization"
    },
    frontier_queued: {
      tone: "muted",
      label: "frontier queued"
    },
    frontier_visit: {
      tone: "active",
      label: "frontier visit"
    },
    code_generated: {
      tone: "active",
      label: "worker generated"
    },
    execution_completed: {
      tone: "muted",
      label: "execution"
    },
    verification_completed: {
      tone: "active",
      label: "verification"
    },
    critique_completed: {
      tone: "active",
      label: "critique"
    },
    repair_triggered: {
      tone: "warn",
      label: "repair"
    },
    search_completed: {
      tone: "success",
      label: "certificate"
    },
    search_exhausted: {
      tone: "warn",
      label: "exhausted"
    },
    search_cancelled: {
      tone: "warn",
      label: "cancelled"
    },
    symbolic_proof: {
      tone: "success",
      label: "symbolic proof"
    },
    error: {
      tone: "error",
      label: "error"
    }
  };
  const KIND_LABELS = {
    algebraic_identity_counterassignment: "algebraic identity",
    finite_group_identity_countermodel: "finite group",
    planar_constant_determinant_collision: "planar Jacobian"
  };
  const DEFAULT_BUDGET = {
    time_seconds: 30,
    max_frontier_visits: 120,
    execution_timeout_seconds: 10,
    max_group_order: 6
  };
  const pad = value => value < 10 ? "0" + value : String(value);
  const clockText = date => pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
  const secondsToText = value => {
    const number = typeof value === "number" ? value : Number.parseFloat(String(value));
    if (!Number.isFinite(number)) return "0.00";
    return number.toFixed(2);
  };
  const slugify = text => {
    const slug = String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return (slug || "certificate").slice(0, 60);
  };
  const downloadText = (filename, text, mime) => {
    const blob = new Blob([text], {
      type: mime + ";charset=utf-8"
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  };
  const copyText = async text => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    document.body.removeChild(area);
    return copied;
  };
  const sha256Hex = async text => {
    if (!window.crypto || !window.crypto.subtle) return null;
    try {
      const payload = new TextEncoder().encode(text);
      const digest = await window.crypto.subtle.digest("SHA-256", payload);
      const bytes = Array.from(new Uint8Array(digest));
      return bytes.map(value => value.toString(16).padStart(2, "0")).join("");
    } catch (error) {
      return null;
    }
  };
  const readHistory = () => {
    try {
      const raw = window.localStorage.getItem(HISTORY_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter(item => item && typeof item.query === "string").slice(0, HISTORY_LIMIT);
    } catch (error) {
      return [];
    }
  };
  const writeHistory = entries => {
    try {
      window.localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, HISTORY_LIMIT)));
    } catch (error) {
      return;
    }
  };
  const parseFrame = frame => {
    const lines = String(frame).split("\n");
    let eventName = "message";
    const dataLines = [];
    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) eventName = line.slice(6).trim();else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (dataLines.length === 0) return null;
    const payload = dataLines.join("\n");
    try {
      const parsed = JSON.parse(payload);
      if (parsed && typeof parsed === "object") {
        if (!parsed.type) parsed.type = eventName;
        return parsed;
      }
      return {
        type: eventName,
        value: parsed
      };
    } catch (error) {
      return {
        type: "error",
        message: "the stream delivered an unparsable frame",
        raw: payload.slice(0, 400)
      };
    }
  };
  const streamSearch = async ({
    query,
    budget,
    signal,
    onEvent
  }) => {
    const response = await fetch(STREAM_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream"
      },
      body: JSON.stringify({
        query,
        budget
      }),
      signal
    });
    if (!response.ok || !response.body) {
      let detail = "";
      try {
        const payload = await response.json();
        detail = payload.error || payload.detail || "";
      } catch (error) {
        detail = response.statusText || "";
      }
      throw new Error(detail ? response.status + ": " + detail : "stream request failed with status " + response.status);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, {
        stream: true
      });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseFrame(frame);
        if (event) onEvent(event);
        boundary = buffer.indexOf("\n\n");
      }
    }
    buffer += decoder.decode();
    const tail = parseFrame(buffer);
    if (tail) onEvent(tail);
  };
  const requestFormalization = async (query, budget, signal) => {
    const response = await fetch(FORMALIZE_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json"
      },
      body: JSON.stringify({
        query,
        budget
      }),
      signal
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload && (payload.error || payload.detail) ? payload.error || payload.detail : "formalization failed";
      throw new Error(detail);
    }
    if (!payload || payload.accepted !== true) {
      throw new Error("the server rejected the formalization request");
    }
    return payload;
  };
  const Tex = ({
    latex,
    display,
    className
  }) => {
    const rendered = useMemo(() => {
      const source = String(latex || "");
      if (!source) return null;
      if (!window.katex || typeof window.katex.renderToString !== "function") return null;
      try {
        const html = window.katex.renderToString(source, {
          displayMode: Boolean(display),
          throwOnError: false,
          strict: false,
          trust: false,
          output: "htmlAndMathml"
        });
        return {
          __html: html
        };
      } catch (error) {
        return null;
      }
    }, [latex, display]);
    if (rendered) return h("span", {
      className: className,
      dangerouslySetInnerHTML: rendered
    });
    return h("code", {
      className: "tex-fallback " + (className || "")
    }, String(latex || ""));
  };
  const Badge = ({
    tone,
    children
  }) => h("span", {
    className: "badge badge-" + (tone || "neutral")
  }, children);
  const Field = ({
    label,
    children,
    wide
  }) => h("div", {
    className: "field" + (wide ? " field-wide" : "")
  }, h("span", {
    className: "field-label"
  }, label), h("span", {
    className: "field-value"
  }, children));
  const Toggle = ({
    label,
    hint,
    value,
    onChange
  }) => h("div", {
    className: "toggle-row"
  }, h("div", {
    className: "toggle-text"
  }, h("span", {
    className: "toggle-label"
  }, label), hint ? h("span", {
    className: "toggle-hint"
  }, hint) : null), h(GlassSwitch, {
    value: Boolean(value),
    onChange
  }));
  const StatTile = ({
    label,
    value,
    tone
  }) => h("div", {
    className: "stat-tile"
  }, h("span", {
    className: "stat-value " + (tone ? "stat-" + tone : "")
  }, value), h("span", {
    className: "stat-label"
  }, label));
  const drawBackground = (ctx, elapsed) => {
    const canvas = ctx.canvas;
    const width = canvas.width;
    const height = canvas.height;
    const time = elapsed / 1000;
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#05070f");
    gradient.addColorStop(0.45, "#0a1024");
    gradient.addColorStop(1, "#04060d");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
    const blobs = [{
      hue: "56, 189, 248",
      x: 0.24,
      y: 0.28,
      radius: 0.42,
      speed: 0.42,
      phase: 0
    }, {
      hue: "167, 139, 250",
      x: 0.74,
      y: 0.32,
      radius: 0.38,
      speed: -0.33,
      phase: 1.7
    }, {
      hue: "244, 114, 182",
      x: 0.56,
      y: 0.78,
      radius: 0.46,
      speed: 0.26,
      phase: 3.1
    }, {
      hue: "34, 211, 238",
      x: 0.14,
      y: 0.82,
      radius: 0.3,
      speed: -0.51,
      phase: 4.4
    }];
    ctx.globalCompositeOperation = "lighter";
    for (let index = 0; index < blobs.length; index++) {
      const blob = blobs[index];
      const drift = Math.sin(time * blob.speed + blob.phase);
      const driftTwo = Math.cos(time * blob.speed * 0.7 + blob.phase);
      const centreX = (blob.x + drift * 0.06) * width;
      const centreY = (blob.y + driftTwo * 0.05) * height;
      const radius = blob.radius * Math.max(width, height) * (0.92 + 0.08 * drift);
      const glow = ctx.createRadialGradient(centreX, centreY, 0, centreX, centreY, radius);
      glow.addColorStop(0, "rgba(" + blob.hue + ", 0.34)");
      glow.addColorStop(0.5, "rgba(" + blob.hue + ", 0.12)");
      glow.addColorStop(1, "rgba(" + blob.hue + ", 0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, width, height);
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.strokeStyle = "rgba(148, 163, 184, 0.06)";
    ctx.lineWidth = 1;
    const spacing = 56;
    const offsetX = time * 6 % spacing;
    const offsetY = time * 4 % spacing;
    ctx.beginPath();
    for (let x = -spacing + offsetX; x < width + spacing; x += spacing) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
    }
    for (let y = -spacing + offsetY; y < height + spacing; y += spacing) {
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
    }
    ctx.stroke();
    const vignette = ctx.createRadialGradient(width * 0.5, height * 0.45, Math.min(width, height) * 0.2, width * 0.5, height * 0.5, Math.max(width, height) * 0.75);
    vignette.addColorStop(0, "rgba(2, 4, 10, 0)");
    vignette.addColorStop(1, "rgba(2, 4, 10, 0.72)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, width, height);
  };
  const useMediaQuery = query => {
    const [matches, setMatches] = useState(() => typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false);
    useEffect(() => {
      if (typeof window.matchMedia !== "function") return undefined;
      const list = window.matchMedia(query);
      const handler = event => setMatches(event.matches);
      setMatches(list.matches);
      if (typeof list.addEventListener === "function") {
        list.addEventListener("change", handler);
        return () => list.removeEventListener("change", handler);
      }
      list.addListener(handler);
      return () => list.removeListener(handler);
    }, [query]);
    return matches;
  };
  const BackgroundStage = ({
    frozen,
    lensX,
    lensY
  }) => {
    const lensSize = 190;
    const specs = useMemo(() => [{
      x: lensX,
      y: lensY,
      lensW: lensSize / 2,
      lensH: lensSize / 2,
      scale: 1,
      opacity: 1
    }, {
      x: 0.82,
      y: 0.16,
      lensW: 120,
      lensH: 104,
      scale: 1,
      opacity: 0.72
    }, {
      x: 0.16,
      y: 0.86,
      lensW: 104,
      lensH: 120,
      scale: 1,
      opacity: 0.6
    }], [lensX, lensY]);
    const draw = useCallback((ctx, elapsed) => drawBackground(ctx, frozen ? 2400 : elapsed), [frozen]);
    return h(Glass, {
      draw: draw,
      lenses: specs,
      maxDpr: 1,
      style: {
        position: "fixed",
        inset: 0,
        zIndex: 0,
        pointerEvents: "none"
      },
      lens: {
        strength: 0.075,
        depth: 0.7,
        curvature: 0.55,
        dispersion: 0.55,
        bend: 0.5,
        bendWidth: 0.18,
        frost: 2,
        sheen: 0.4,
        sheenAngle: 42,
        glow: 0.16,
        glowSpread: 1.1,
        glowFalloff: 0.6,
        specular: 1,
        brightness: 0.02
      }
    });
  };
  const Card = ({
    className,
    children,
    optics,
    ...rest
  }) => h(GlassMaterial, Object.assign({
    className: "card " + (className || ""),
    optics: Object.assign({
      mapSize: 256,
      frost: 12,
      saturate: 1.18,
      depth: 0.4,
      strength: 0.045,
      bend: 0.5,
      dispersion: 0.3,
      sheen: 0.28,
      glow: 0.1,
      brightness: 0.015
    }, optics || {})
  }, rest), children);
  const SectionTitle = ({
    title,
    caption,
    aside
  }) => h("div", {
    className: "section-title"
  }, h("div", null, h("h2", null, title), caption ? h("p", {
    className: "section-caption"
  }, caption) : null), aside || null);
  const PipelineStrip = ({
    states,
    activeStep
  }) => h("ol", {
    className: "pipeline"
  }, PIPELINE_STEPS.map(step => h("li", {
    key: step.id,
    className: "pipeline-step pipeline-" + (states[step.id] || "idle") + (activeStep === step.id ? " pipeline-active" : "")
  }, h("span", {
    className: "pipeline-dot"
  }), h("span", {
    className: "pipeline-label"
  }, step.label))));
  const ProgressRail = ({
    elapsed,
    budgetSeconds,
    progress,
    running,
    onCancel
  }) => {
    const safeProgress = Math.max(0, Math.min(1, progress));
    const remaining = running && safeProgress > 0.02 ? Math.max(0, elapsed * (1 - safeProgress) / safeProgress) : null;
    return h("div", {
      className: "progress-wrap"
    }, h("div", {
      className: "progress-head"
    }, h("span", null, running ? "search running" : "idle"), h("span", {
      className: "progress-timing"
    }, secondsToText(elapsed) + " s / " + String(budgetSeconds) + " s" + (remaining == null ? "" : " · ETA " + secondsToText(remaining) + " s"))), h("div", {
      className: "progress-track"
    }, h("div", {
      className: "progress-fill",
      style: {
        width: (safeProgress * 100).toFixed(2) + "%"
      }
    })), running ? h("button", {
      type: "button",
      className: "ghost-button",
      onClick: onCancel
    }, "Cancel search") : null);
  };
  const FormTabs = ({
    formalization,
    symbolicProof
  }) => {
    const rows = [];
    if (!formalization) {
      return h("div", {
        className: "empty-state"
      }, h("p", null, "No statement has been formalized yet."), h("p", {
        className: "dim"
      }, "Write a mathematical claim and start the search; the formalized target appears here before the first frontier is visited."));
    }
    rows.push(h("p", {
      className: "statement",
      key: "statement"
    }, h(Tex, {
      latex: formalization.statement.latex,
      display: true
    })));
    rows.push(h("div", {
      className: "field-grid",
      key: "fields"
    }, h(Field, {
      label: "Problem kind"
    }, h(Badge, {
      tone: "kind"
    }, KIND_LABELS[formalization.problem_kind] || formalization.problem_kind)), formalization.variables.length ? h(Field, {
      label: "Variables"
    }, formalization.variables.map(item => item.name).join(", ")) : null, formalization.left_expression ? h(Field, {
      label: "Left side"
    }, h(Tex, {
      latex: formalization.left_latex
    })) : null, formalization.right_expression ? h(Field, {
      label: "Right side"
    }, h(Tex, {
      latex: formalization.right_latex
    })) : null, formalization.left_word ? h(Field, {
      label: "Left word"
    }, h(Tex, {
      latex: formalization.left_latex
    })) : null, formalization.right_word ? h(Field, {
      label: "Right word"
    }, h(Tex, {
      latex: formalization.right_latex
    })) : null, formalization.identity_symbol ? h(Field, {
      label: "Identity symbol"
    }, h(Tex, {
      latex: formalization.identity_symbol_latex
    })) : null, formalization.order_bounds ? h(Field, {
      label: "Declared order"
    }, String(formalization.order_bounds.declared)) : null, formalization.order_bounds ? h(Field, {
      label: "Effective order"
    }, String(formalization.order_bounds.effective)) : null, formalization.determinant_requirement ? h(Field, {
      label: "Determinant requirement"
    }, h(Tex, {
      latex: formalization.determinant_requirement
    })) : null, formalization.components && formalization.components.length ? h(Field, {
      label: "Components"
    }, formalization.components.map(item => item.latex).join(", ")) : null));
    if (formalization.constraints && formalization.constraints.length) {
      rows.push(h("div", {
        className: "constraint-row",
        key: "constraints"
      }, h("span", {
        className: "field-label"
      }, "Constraints"), formalization.constraints.map((item, index) => h("span", {
        className: "chip",
        key: index
      }, h(Tex, {
        latex: item.latex
      })))));
    }
    if (formalization.domain_obligations && formalization.domain_obligations.length) {
      rows.push(h("div", {
        className: "obligation-row",
        key: "obligations"
      }, h("span", {
        className: "field-label"
      }, "Pole and domain obligations"), formalization.domain_obligations.map((item, index) => h("span", {
        className: "chip chip-warn",
        key: index
      }, h(Tex, {
        latex: item.latex
      }) + " ≠ 0"))));
    }
    if (symbolicProof) {
      rows.push(h("div", {
        className: "notice notice-success",
        key: "proof-notice"
      }, h("strong", null, "Symbolic decision"), h("span", null, "The exact difference of the two sides vanishes identically, so no counterassignment exists.")));
    }
    return h("div", {
      className: "stack"
    }, rows);
  };
  const AlgebraicResult = ({
    result
  }) => {
    const block = result.algebraic;
    return h("div", {
      className: "stack"
    }, h("div", {
      className: "result-headline"
    }, h(Tex, {
      latex: result.headline_latex,
      display: true
    })), h("div", {
      className: "assignment-row"
    }, Object.keys(block.assignments).sort().map(name => h("span", {
      className: "assignment",
      key: name
    }, h("span", {
      className: "assignment-name"
    }, name), h("span", {
      className: "assignment-value"
    }, h(Tex, {
      latex: block.assignments_latex[name]
    }))))), h("div", {
      className: "field-grid"
    }, h(Field, {
      label: "Left side",
      wide: true
    }, h(Tex, {
      latex: block.left_source_latex || block.left_latex
    })), h(Field, {
      label: "Right side",
      wide: true
    }, h(Tex, {
      latex: block.right_source_latex || block.right_latex
    })), h(Field, {
      label: "Left value",
      wide: true
    }, h(Tex, {
      latex: block.left_value_latex
    })), h(Field, {
      label: "Right value",
      wide: true
    }, h(Tex, {
      latex: block.right_value_latex
    })), h(Field, {
      label: "Difference",
      wide: true
    }, h(Tex, {
      latex: block.difference_latex
    }))), block.domain_obligations.length ? h("div", {
      className: "table-block"
    }, h("span", {
      className: "field-label"
    }, "Domain obligations at the counterassignment"), h("table", {
      className: "data-table"
    }, h("thead", null, h("tr", null, h("th", null, "obligation"), h("th", null, "exact value"), h("th", null, "status"))), h("tbody", null, block.domain_obligations.map((item, index) => h("tr", {
      key: index
    }, h("td", null, h(Tex, {
      latex: item.latex
    })), h("td", null, item.value_latex ? h(Tex, {
      latex: item.value_latex
    }) : h("span", {
      className: "dim"
    }, "n/a")), h("td", null, item.satisfied ? h(Badge, {
      tone: "pass"
    }, "satisfied") : h(Badge, {
      tone: "fail"
    }, "violated"))))))) : null, h("pre", {
      className: "exact-output"
    }, result.formatted_text));
  };
  const GroupResult = ({
    result
  }) => {
    const block = result.group;
    const table = block.cayley_table || [];
    return h("div", {
      className: "stack"
    }, h("div", {
      className: "result-headline"
    }, h(Tex, {
      latex: result.headline_latex,
      display: true
    })), h("div", {
      className: "field-grid"
    }, h(Field, {
      label: "Group order"
    }, String(block.order)), h(Field, {
      label: "Identity"
    }, h(Tex, {
      latex: block.identity_symbol_latex
    }) + " = " + String(block.identity_element)), h(Field, {
      label: "Left word"
    }, h(Tex, {
      latex: block.left_latex
    }) + " = " + String(block.left_value)), h(Field, {
      label: "Right word"
    }, h(Tex, {
      latex: block.right_latex
    }) + " = " + String(block.right_value)), h(Field, {
      label: "Group family"
    }, block.group_family || "constructed table"), h(Field, {
      label: "Exponent"
    }, String(block.invariants.exponent)), h(Field, {
      label: "Abelian"
    }, block.invariants.abelian ? "yes" : "no"), h(Field, {
      label: "Cyclic"
    }, block.invariants.cyclic ? "yes" : "no")), h("div", {
      className: "table-block"
    }, h("span", {
      className: "field-label"
    }, "Cayley table (row × column)"), h("div", {
      className: "cayley-scroll"
    }, h("table", {
      className: "cayley-table"
    }, h("thead", null, h("tr", null, h("th", {
      className: "cayley-corner"
    }, "·"), block.elements.map(element => h("th", {
      key: "h" + element,
      className: "cayley-head"
    }, String(element))))), h("tbody", null, table.map((row, rowIndex) => h("tr", {
      key: "r" + rowIndex
    }, h("th", {
      className: "cayley-head"
    }, String(rowIndex)), row.map((value, columnIndex) => {
      const isIdentityCell = rowIndex === block.identity_element || columnIndex === block.identity_element;
      const isAssignment = Object.values(block.assignments).includes(rowIndex) && Object.values(block.assignments).includes(columnIndex);
      return h("td", {
        key: "c" + rowIndex + "-" + columnIndex,
        className: "cayley-cell" + (isIdentityCell ? " cayley-identity" : "") + (isAssignment ? " cayley-assignment" : "")
      }, String(value));
    }))))))), h("div", {
      className: "table-block"
    }, h("span", {
      className: "field-label"
    }, "Word evaluations"), h("table", {
      className: "data-table"
    }, h("thead", null, h("tr", null, h("th", null, "word"), h("th", null, "evaluator"), h("th", null, "value"))), h("tbody", null, block.word_evaluations.map((item, index) => h("tr", {
      key: index
    }, h("td", null, h(Tex, {
      latex: item.latex
    })), h("td", null, item.form), h("td", null, String(item.value))))))), h("div", {
      className: "chip-row"
    }, h("span", {
      className: "field-label"
    }, "Element orders"), block.invariants.element_orders.map((order, index) => h("span", {
      className: "chip",
      key: index
    }, String(index) + " → " + String(order)))), h("pre", {
      className: "exact-output"
    }, result.formatted_text));
  };
  const PlanarResult = ({
    result
  }) => {
    const block = result.planar;
    return h("div", {
      className: "stack"
    }, h("div", {
      className: "result-headline"
    }, h(Tex, {
      latex: result.headline_latex,
      display: true
    })), h("div", {
      className: "planar-map"
    }, h(Tex, {
      latex: block.map_latex,
      display: true
    })), h("div", {
      className: "field-grid"
    }, h(Field, {
      label: "Point P",
      wide: true
    }, h(Tex, {
      latex: block.point_p_latex
    })), h(Field, {
      label: "Point Q",
      wide: true
    }, h(Tex, {
      latex: block.point_q_latex
    })), h(Field, {
      label: "Constant determinant",
      wide: true
    }, h(Tex, {
      latex: block.jacobian_determinant_latex
    })), h(Field, {
      label: "Independent path",
      wide: true
    }, h(Tex, {
      latex: block.independent_determinant_latex
    })), h(Field, {
      label: "Runtime route"
    }, block.runtime_route || "n/a"), h(Field, {
      label: "Composition"
    }, block.composition_scheme || "n/a"), h(Field, {
      label: "Symmetry"
    }, block.symmetry_mode || "n/a"), h(Field, {
      label: "Distinct points"
    }, block.distinct_points ? "proved" : "not proved")), h("div", {
      className: "table-block"
    }, h("span", {
      className: "field-label"
    }, "Collision equations"), h("table", {
      className: "data-table"
    }, h("thead", null, h("tr", null, h("th", null, "component"), h("th", null, "at P"), h("th", null, "at Q"), h("th", null, "difference"))), h("tbody", null, block.collision_rows.map((item, index) => h("tr", {
      key: index
    }, h("td", null, item.label), h("td", null, h(Tex, {
      latex: item.at_point
    })), h("td", null, h(Tex, {
      latex: item.at_other
    })), h("td", null, h(Tex, {
      latex: item.difference
    }))))))), block.domain_obligations.length ? h("div", {
      className: "table-block"
    }, h("span", {
      className: "field-label"
    }, "Component domain obligations"), h("table", {
      className: "data-table"
    }, h("thead", null, h("tr", null, h("th", null, "obligation"), h("th", null, "values"), h("th", null, "status"))), h("tbody", null, block.domain_obligations.map((item, index) => h("tr", {
      key: index
    }, h("td", null, h(Tex, {
      latex: item.latex
    })), h("td", null, item.values.map((value, valueIndex) => h(Tex, {
      key: valueIndex,
      latex: value
    }))), h("td", null, item.satisfied ? h(Badge, {
      tone: "pass"
    }, "satisfied") : h(Badge, {
      tone: "fail"
    }, "violated"))))))) : null, h("pre", {
      className: "exact-output"
    }, result.formatted_text));
  };
  const ExhaustionResult = ({
    result
  }) => {
    const block = result.exhaustion;
    return h("div", {
      className: "stack"
    }, h("div", {
      className: "result-headline"
    }, h("span", null, result.headline || "no counterexample found within the search budget")), h("div", {
      className: "field-grid"
    }, h(Field, {
      label: "Reason"
    }, block.exhaustion_reason), h(Field, {
      label: "Frontiers visited"
    }, String(block.frontiers_examined)), h(Field, {
      label: "Candidates verified"
    }, String(block.candidates_verified)), h(Field, {
      label: "Mutation rounds"
    }, String(block.mutation_rounds)), h(Field, {
      label: "Repair rounds"
    }, String(block.repairs)), h(Field, {
      label: "Lanes explored"
    }, String(block.lane_count)), h(Field, {
      label: "Wall clock budget"
    }, String(block.budget_fields.time_seconds) + " s"), h(Field, {
      label: "Worker timeout"
    }, String(block.budget_fields.execution_timeout_seconds) + " s")), block.lanes.length ? h("div", {
      className: "table-block"
    }, h("span", {
      className: "field-label"
    }, "Lane coverage"), h("table", {
      className: "data-table"
    }, h("thead", null, h("tr", null, h("th", null, "lane"), h("th", null, "visits"), h("th", null, "candidates"), h("th", null, "repairs"))), h("tbody", null, block.lanes.map((item, index) => h("tr", {
      key: index
    }, h("td", null, item.lane), h("td", null, String(item.visits)), h("td", null, String(item.candidates)), h("td", null, String(item.repairs))))))) : null, block.note ? h("div", {
      className: "notice notice-warn"
    }, h("strong", null, "Open problem"), h("span", null, block.note)) : null, h("pre", {
      className: "exact-output"
    }, result.formatted_text));
  };
  const ProofResult = ({
    result
  }) => {
    const block = result.proof;
    return h("div", {
      className: "stack"
    }, h("div", {
      className: "result-headline"
    }, h("span", null, "no counterassignment exists")), h("p", {
      className: "statement"
    }, h(Tex, {
      latex: result.statement.latex,
      display: true
    })), h("ol", {
      className: "proof-steps"
    }, block.steps.map((step, index) => h("li", {
      key: index
    }, h("div", {
      className: "proof-step-head"
    }, h("strong", null, step.label)), h("div", {
      className: "proof-step-math"
    }, h(Tex, {
      latex: step.latex,
      display: true
    })), h("p", {
      className: "dim"
    }, step.detail)))), h("div", {
      className: "field-grid"
    }, h(Field, {
      label: "Reason"
    }, block.reason), h(Field, {
      label: "Decision engine"
    }, result.provenance.executor)), h("pre", {
      className: "exact-output"
    }, result.formatted_text));
  };
  const ResultCard = ({
    result,
    running
  }) => {
    if (!result) {
      return h("div", {
        className: "empty-state"
      }, h("p", null, running ? "Search in progress." : "No certificate yet."), h("p", {
        className: "dim"
      }, running ? "Frontiers, workers and verification results stream in above." : "Every finished search reports either an exact certificate, a symbolic decision or an honest exhaustion report."));
    }
    if (result.kind === "counterexample") {
      if (result.problem_kind === "finite_group_identity_countermodel") return h(GroupResult, {
        result
      });
      if (result.problem_kind === "planar_constant_determinant_collision") return h(PlanarResult, {
        result
      });
      return h(AlgebraicResult, {
        result
      });
    }
    if (result.kind === "symbolic_proof") return h(ProofResult, {
      result
    });
    return h(ExhaustionResult, {
      result
    });
  };
  const AuditList = ({
    entries,
    digestCheck
  }) => {
    const rows = entries.slice();
    if (digestCheck && digestCheck.state !== "idle") {
      rows.push({
        id: "worker_sha256_client",
        label: "Worker SHA-256 recomputed in the browser",
        status: digestCheck.state === "pass" ? "pass" : digestCheck.state === "fail" ? "fail" : "warn",
        detail: digestCheck.state === "pass" ? "the browser recomputed the SHA-256 digest of the received worker source and it matches" : digestCheck.state === "fail" ? "the recomputed digest does not match the digest reported by the server" : "the browser cannot compute SHA-256 digests in this context",
        value: digestCheck.digest ? digestCheck.digest.slice(0, 16) : ""
      });
    }
    if (!rows.length) {
      return h("div", {
        className: "empty-state"
      }, h("p", {
        className: "dim"
      }, "Verification rows appear as soon as a candidate is certified."));
    }
    return h("ul", {
      className: "audit-list"
    }, rows.map((entry, index) => h("li", {
      key: entry.id + index,
      className: "audit-row audit-" + entry.status
    }, h("span", {
      className: "audit-mark"
    }, entry.status === "pass" ? "✓" : entry.status === "fail" ? "✕" : entry.status === "warn" ? "!" : "•"), h("div", {
      className: "audit-body"
    }, h("div", {
      className: "audit-head"
    }, h("span", {
      className: "audit-label"
    }, entry.label), entry.value ? h("code", {
      className: "audit-value"
    }, entry.value) : null), h("p", {
      className: "audit-detail"
    }, entry.detail), h("code", {
      className: "audit-id"
    }, entry.id)))));
  };
  const ExportToolbar = ({
    result,
    onToast
  }) => {
    if (!result) {
      return h("div", {
        className: "empty-state"
      }, h("p", {
        className: "dim"
      }, "Exports become available with the certificate."));
    }
    const exports = result.exports || {};
    const base = exports.base_filename || "exact-formula-search";
    const items = [{
      key: "latex-copy",
      label: "Copy LaTeX",
      enabled: Boolean(exports.latex),
      run: async () => (await copyText(exports.latex)) ? "LaTeX copied" : "clipboard unavailable"
    }, {
      key: "latex-download",
      label: "Download .tex",
      enabled: Boolean(exports.latex),
      run: () => {
        downloadText(base + ".tex", exports.latex, "application/x-tex");
        return "certificate.tex downloaded";
      }
    }, {
      key: "sympy-copy",
      label: "Copy SymPy script",
      enabled: Boolean(exports.sympy),
      run: async () => (await copyText(exports.sympy)) ? "SymPy script copied" : "clipboard unavailable"
    }, {
      key: "sympy-download",
      label: "Download .py",
      enabled: Boolean(exports.sympy),
      run: () => {
        downloadText(base + ".py", exports.sympy, "text/x-python");
        return "reproduction script downloaded";
      }
    }, {
      key: "json-copy",
      label: "Copy JSON",
      enabled: Boolean(exports.json),
      run: async () => (await copyText(exports.json)) ? "certificate JSON copied" : "clipboard unavailable"
    }, {
      key: "json-download",
      label: "Download .json",
      enabled: Boolean(exports.json),
      run: () => {
        downloadText(base + ".json", exports.json, "application/json");
        return "certificate.json downloaded";
      }
    }];
    return h("div", {
      className: "export-toolbar"
    }, items.map(item => h("button", {
      key: item.key,
      type: "button",
      className: "ghost-button",
      disabled: !item.enabled,
      onClick: async () => {
        const message = await item.run();
        onToast(message);
      }
    }, item.label)));
  };
  const StreamLog = ({
    events,
    autoScroll,
    onToggleAutoScroll,
    onClear
  }) => h(GlassMaterial, {
    className: "card card-log",
    optics: {
      mapSize: 192,
      frost: 10,
      depth: 0.35,
      strength: 0.04,
      dispersion: 0.24,
      sheen: 0.22,
      brightness: 0.01
    }
  }, h(SectionTitle, {
    title: "Event stream",
    caption: "every server-sent event of the running search, in arrival order",
    aside: h("div", {
      className: "log-actions"
    }, h(GlassSwitch, {
      value: Boolean(autoScroll),
      onChange: () => onToggleAutoScroll(!autoScroll)
    }), h("span", {
      className: "toggle-hint"
    }, "auto scroll"), h("button", {
      type: "button",
      className: "ghost-button ghost-small",
      onClick: onClear
    }, "Clear"))
  }), h("ol", {
    className: "log-list"
  }, events.map(entry => h("li", {
    key: entry.id,
    className: "log-row log-" + entry.tone
  }, h("span", {
    className: "log-time"
  }, entry.time), h("span", {
    className: "log-tag"
  }, entry.label), h("span", {
    className: "log-message"
  }, entry.message)))));
  const App = () => {
    const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
    const [query, setQuery] = useState("");
    const [presets, setPresets] = useState([]);
    const [health, setHealth] = useState(null);
    const [budget, setBudget] = useState(DEFAULT_BUDGET);
    const [formalization, setFormalization] = useState(null);
    const [events, setEvents] = useState([]);
    const [statistics, setStatistics] = useState(null);
    const [frontier, setFrontier] = useState(null);
    const [pendingFrontiers, setPendingFrontiers] = useState(0);
    const [pipeline, setPipeline] = useState({});
    const [activeStep, setActiveStep] = useState(null);
    const [running, setRunning] = useState(false);
    const [progress, setProgress] = useState(0);
    const [elapsed, setElapsed] = useState(0);
    const [result, setResult] = useState(null);
    const [failure, setFailure] = useState(null);
    const [history, setHistory] = useState(() => readHistory());
    const [toast, setToast] = useState(null);
    const [autoScroll, setAutoScroll] = useState(true);
    const [digestCheck, setDigestCheck] = useState({
      state: "idle",
      digest: ""
    });
    const [showRawEvents, setShowRawEvents] = useState(false);
    const [showWorker, setShowWorker] = useState(false);
    const [workerSource, setWorkerSource] = useState("");
    const abortRef = useRef(null);
    const startedAtRef = useRef(0);
    const timerRef = useRef(0);
    const logRef = useRef(null);
    const eventIdRef = useRef(0);
    const lensX = useMemo(() => glassValue(0.5), []);
    const lensY = useMemo(() => glassValue(0.34), []);
    const statusRef = useRef("idle");
    const groupRowVisible = formalization ? String(formalization.problem_kind).includes("group") : query.toLowerCase().includes("group");
    useEffect(() => {
      let cancelled = false;
      fetch(PRESETS_ENDPOINT, {
        headers: {
          Accept: "application/json"
        }
      }).then(response => response.ok ? response.json() : Promise.reject(new Error("presets unavailable"))).then(payload => {
        if (cancelled) return;
        setPresets(Array.isArray(payload.presets) ? payload.presets : []);
      }).catch(() => {
        if (!cancelled) setPresets([]);
      });
      fetch(HEALTH_ENDPOINT, {
        headers: {
          Accept: "application/json"
        }
      }).then(response => response.ok ? response.json() : Promise.reject(new Error("health unavailable"))).then(payload => {
        if (!cancelled) setHealth(payload);
      }).catch(() => {
        if (!cancelled) setHealth(null);
      });
      return () => {
        cancelled = true;
      };
    }, []);
    useEffect(() => {
      if (!toast) return undefined;
      const timer = setTimeout(() => setToast(null), 3200);
      return () => clearTimeout(timer);
    }, [toast]);
    useEffect(() => {
      const pointer = event => {
        if (reducedMotion) return;
        const width = Math.max(1, window.innerWidth);
        const height = Math.max(1, window.innerHeight);
        const x = Math.max(0.05, Math.min(0.95, event.clientX / width));
        const y = Math.max(0.05, Math.min(0.95, 1 - event.clientY / height));
        animateGlassValue(lensX, x, {
          duration: 0.9,
          ease: window.LiquidGlassEngine.glassEase
        });
        animateGlassValue(lensY, y, {
          duration: 0.9,
          ease: window.LiquidGlassEngine.glassEase
        });
      };
      window.addEventListener("pointermove", pointer, {
        passive: true
      });
      return () => window.removeEventListener("pointermove", pointer);
    }, [lensX, lensY, reducedMotion]);
    useEffect(() => {
      if (!running) return undefined;
      timerRef.current = window.setInterval(() => {
        setElapsed((Date.now() - startedAtRef.current) / 1000);
      }, 120);
      return () => window.clearInterval(timerRef.current);
    }, [running]);
    useEffect(() => {
      if (!autoScroll || !logRef.current) return;
      const node = logRef.current;
      node.scrollTop = node.scrollHeight;
    }, [events, autoScroll]);
    const pushEvent = useCallback((type, message, tone) => {
      eventIdRef.current += 1;
      const meta = EVENT_META[type] || {
        tone: tone || "muted",
        label: type
      };
      setEvents(current => current.concat([{
        id: eventIdRef.current,
        type,
        time: clockText(new Date()),
        label: meta.label,
        tone: tone || meta.tone,
        message
      }]).slice(-400));
    }, []);
    const markStep = useCallback((stepId, state) => {
      if (!stepId) return;
      setPipeline(current => current[stepId] === state ? current : Object.assign({}, current, {
        [stepId]: state
      }));
    }, []);
    const describeEvent = useCallback(event => {
      switch (event.type) {
        case "search_started":
          return "budget: " + String(event.budget.time_seconds) + " s wall clock, " + String(event.budget.max_frontier_visits) + " frontier visits, worker timeout " + String(event.budget.execution_timeout_seconds) + " s" + (event.budget.max_group_order ? ", group order bound " + String(event.budget.max_group_order) : "");
        case "formalization":
          return "kind " + event.problem_kind + " · " + event.statement.text;
        case "frontier_queued":
          return "lane " + event.lane + " · degree " + String(event.degree_extent) + " · coefficient " + String(event.coefficient_extent) + " · signature " + event.short_signature;
        case "frontier_visit":
          return "visit " + String(event.statistics.frontiers_examined) + " · lane " + event.lane + " · " + String(event.kind) + " · " + String(event.exact_domain);
        case "code_generated":
          return "worker for " + String(event.frontier_signature).slice(0, 12) + " · " + String(event.line_count) + " lines · sha256 " + String(event.worker_sha256).slice(0, 16);
        case "execution_completed":
          return event.status + " · candidates " + String(event.candidate_count) + (event.failure_reasons.length ? " · reasons " + event.failure_reasons.join(",") : "") + " · " + String(event.execution_seconds) + " s";
        case "verification_completed":
          return (event.passed ? "certified" : "rejected") + " · " + (event.issue_codes.length ? event.issue_codes.join(",") : "no issue codes");
        case "critique_completed":
          return (event.passed ? "clean" : "blocking issue") + " · " + (event.issue_codes.length ? event.issue_codes.join(",") : "no issue codes");
        case "repair_triggered":
          return "reason " + event.reason + " · actions " + (event.repair_actions.length ? event.repair_actions.join(",") : "frontier mutation") + " · new frontiers " + String(event.new_frontier_signatures.length);
        case "search_completed":
          return "certificate: " + event.headline;
        case "search_exhausted":
          return "exhausted · reason " + event.exhaustion.exhaustion_reason + " · frontiers " + String(event.exhaustion.frontiers_examined);
        case "symbolic_proof":
          return "symbolic decision: " + event.proof.reason;
        case "search_cancelled":
          return "cancelled by the client";
        case "error":
          return event.message || "the search failed";
        default:
          return JSON.stringify(event).slice(0, 220);
      }
    }, []);
    const applyEvent = useCallback(event => {
      if (event.type !== "frontier_queued") {
        markStep(PIPELINE_STEPS.find(step => step.events.includes(event.type))?.id, event.type.startsWith("search_completed") || event.type === "search_exhausted" || event.type === "symbolic_proof" ? "done" : "active");
      }
      if (event.type === "frontier_queued") {
        setPendingFrontiers(current => current + 1);
        markStep("queue", "active");
      }
      if (event.type === "frontier_visit") {
        setPendingFrontiers(current => Math.max(0, current - 1));
        setFrontier(event);
        setActiveStep("execute");
        markStep("queue", "done");
        markStep("execute", "active");
      }
      if (event.type === "code_generated") {
        setWorkerSource(String(event.worker_code || ""));
        setDigestCheck({
          state: "checking",
          digest: ""
        });
        sha256Hex(String(event.worker_code || "")).then(digest => {
          if (!digest) setDigestCheck({
            state: "unavailable",
            digest: ""
          });else if (digest === String(event.worker_sha256 || "")) setDigestCheck({
            state: "pass",
            digest
          });else setDigestCheck({
            state: "fail",
            digest
          });
        });
      }
      if (event.type === "verification_completed") {
        markStep("verify", event.passed ? "done" : "warn");
        markStep("execute", "done");
      }
      if (event.type === "critique_completed") {
        markStep("critique", event.passed ? "done" : "warn");
        markStep("verify", "done");
      }
      if (event.type === "repair_triggered") {
        markStep("repair", "active");
      }
      if (event.type === "formalization") {
        setFormalization(event);
        if (event.order_bounds && String(event.problem_kind).includes("group")) {
          setBudget(current => Object.assign({}, current, {
            max_group_order: Math.max(1, Math.min(current.max_group_order, event.order_bounds.declared))
          }));
        }
      }
      if (event.statistics) {
        setStatistics(event.statistics);
        const elapsedValue = Number.parseFloat(String(event.statistics.elapsed_seconds));
        setElapsed(Number.isFinite(elapsedValue) ? elapsedValue : 0);
        const visits = Number(event.statistics.frontiers_examined) || 0;
        const fractional = Math.min(1, visits / Math.max(1, budget.max_frontier_visits));
        setProgress(Math.max(fractional * 0.75, Math.min(0.97, Number.parseFloat(String(event.statistics.elapsed_seconds)) / Math.max(1, budget.time_seconds) * 0.9)));
      }
      if (event.type === "search_completed" || event.type === "search_exhausted" || event.type === "symbolic_proof") {
        setResult(event);
        setProgress(1);
        markStep("certify", event.type === "search_completed" || event.type === "symbolic_proof" ? "done" : "warn");
        if (event.statistics) setStatistics(event.statistics);
        setHistory(current => {
          const entry = {
            id: String(Date.now()) + "-" + Math.random().toString(16).slice(2, 8),
            query,
            at: new Date().toISOString(),
            kind: event.kind,
            problem_kind: event.problem_kind,
            headline: event.headline,
            seconds: event.runtime_seconds
          };
          const next = [entry].concat(current.filter(item => item.query !== query)).slice(0, HISTORY_LIMIT);
          writeHistory(next);
          return next;
        });
      }
      if (event.type === "search_cancelled") {
        setProgress(0);
      }
    }, [budget, markStep, query]);
    const stopSearch = useCallback(cancelled => {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = null;
      setRunning(false);
      setActiveStep(null);
      statusRef.current = "idle";
      if (cancelled) {
        pushEvent("search_cancelled", "the search was cancelled by the user", "warn");
        markStep("certify", "warn");
      }
    }, [markStep, pushEvent]);
    const startSearch = useCallback(async (requestedQuery, requestedBudget) => {
      const text = String(requestedQuery == null ? query : requestedQuery).trim();
      if (!text) {
        setFailure("Write a mathematical statement before starting the search.");
        return;
      }
      if (running) return;
      setQuery(text);
      setFailure(null);
      setResult(null);
      setFormalization(null);
      setStatistics(null);
      setFrontier(null);
      setPendingFrontiers(0);
      setPipeline({});
      setProgress(0);
      setElapsed(0);
      setDigestCheck({
        state: "idle",
        digest: ""
      });
      setWorkerSource("");
      setRunning(true);
      statusRef.current = "running";
      startedAtRef.current = Date.now();
      if (requestedBudget) setBudget(current => Object.assign({}, current, requestedBudget));
      const controller = new AbortController();
      abortRef.current = controller;
      const requestBudget = Object.assign({}, budget, requestedBudget || {});
      if (requestedBudget && requestedBudget.max_group_order) requestBudget.max_group_order = requestedBudget.max_group_order;
      if (!groupRowVisible && !(requestedBudget && requestedBudget.max_group_order)) delete requestBudget.max_group_order;
      pushEvent("search_started", "request accepted for: " + text, "info");
      try {
        const described = await requestFormalization(text, requestBudget, controller.signal);
        setFormalization(described);
        if (described.order_bounds && String(described.problem_kind).includes("group")) {
          setBudget(current => Object.assign({}, current, {
            max_group_order: Math.max(1, described.order_bounds.declared)
          }));
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        setFailure(String(error.message || error));
        setRunning(false);
        setActiveStep(null);
        pushEvent("error", String(error.message || error), "error");
        return;
      }
      try {
        await streamSearch({
          query: text,
          budget: requestBudget,
          signal: controller.signal,
          onEvent: event => {
            applyEvent(event);
            pushEvent(event.type, describeEvent(event));
            if (event.type === "error") setFailure(String(event.message || "the engine reported an internal failure"));
          }
        });
        setRunning(false);
        setActiveStep(null);
        statusRef.current = "idle";
      } catch (error) {
        if (controller.signal.aborted) return;
        setFailure(String(error.message || error));
        pushEvent("error", String(error.message || error), "error");
        setRunning(false);
        setActiveStep(null);
        statusRef.current = "idle";
      } finally {
        abortRef.current = null;
      }
    }, [applyEvent, budget, describeEvent, groupRowVisible, pushEvent, query, running]);
    useEffect(() => {
      const handler = event => {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
          event.preventDefault();
          startSearch();
        } else if (event.key === "Escape" && statusRef.current === "running") {
          stopSearch(true);
        }
      };
      window.addEventListener("keydown", handler);
      return () => window.removeEventListener("keydown", handler);
    }, [startSearch, stopSearch]);
    const usePreset = useCallback(preset => {
      setQuery(preset.query);
      startSearch(preset.query, preset.budget || null);
    }, [startSearch]);
    const formalizedResult = result && result.kind;
    const budgetSeconds = Number(budget.time_seconds) || DEFAULT_BUDGET.time_seconds;
    const progressValue = running ? progress : result ? 1 : 0;
    return h(React.Fragment, null, h(BackgroundStage, {
      frozen: reducedMotion,
      lensX,
      lensY
    }), h("div", {
      className: "shell"
    }, h("header", {
      className: "topbar"
    }, h("div", {
      className: "brand"
    }, h("span", {
      className: "brand-mark"
    }, "λ"), h("div", null, h("h1", null, "Exact Formula Search"), h("p", {
      className: "brand-sub"
    }, "exact rational algebra · finite group countermodels · planar determinant collisions"))), h("div", {
      className: "topbar-meta"
    }, h(Badge, {
      tone: running ? "active" : "neutral"
    }, running ? "search running" : "ready"), health ? h("span", {
      className: "meta-line"
    }, "engine " + String(health.version) + " · assets " + String(health.assets)) : h("span", {
      className: "meta-line"
    }, "engine offline"))), h("main", {
      className: "layout"
    }, h("section", {
      className: "column column-left"
    }, h(Card, {
      className: "card-composer"
    }, h(SectionTitle, {
      title: "Statement",
      caption: "written statement, formalized exactly before any search runs"
    }), h("textarea", {
      className: "composer-input",
      value: query,
      spellCheck: false,
      placeholder: "e.g. In every finite group of order at most 8, x*y = y*x",
      onChange: event => setQuery(event.target.value),
      onKeyDown: event => {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
          event.preventDefault();
          startSearch();
        }
      },
      rows: 4
    }), h("div", {
      className: "composer-actions"
    }, h("button", {
      type: "button",
      className: "primary-button",
      disabled: running,
      onClick: () => startSearch()
    }, running ? "Searching…" : "Start exact search"), running ? h("button", {
      type: "button",
      className: "ghost-button",
      onClick: () => stopSearch(true)
    }, "Cancel") : null, h("span", {
      className: "shortcut"
    }, "Ctrl/⌘ + Enter")), h(ProgressRail, {
      elapsed,
      budgetSeconds,
      progress: progressValue,
      running,
      onCancel: () => stopSearch(true)
    }), h("div", {
      className: "telemetry"
    }, h(StatTile, {
      label: "frontiers",
      value: statistics ? String(statistics.frontiers_examined) : "0"
    }), h(StatTile, {
      label: "candidates",
      value: statistics ? String(statistics.candidates_verified) : "0"
    }), h(StatTile, {
      label: "repairs",
      value: statistics ? String(statistics.repairs) : "0"
    }), h(StatTile, {
      label: "lanes",
      value: statistics ? String(statistics.lane_count) : "0"
    }), h(StatTile, {
      label: "queued",
      value: String(pendingFrontiers)
    }), h(StatTile, {
      label: "elapsed",
      value: secondsToText(elapsed) + " s"
    })), frontier ? h("div", {
      className: "frontier-readout"
    }, h("span", {
      className: "field-label"
    }, "current frontier"), h("code", null, frontier.lane + " · " + frontier.kind + " · deg " + String(frontier.degree_extent) + " · coeff " + String(frontier.coefficient_extent) + " · " + frontier.exact_domain + " · " + frontier.solver_route)) : null), h(Card, {
      className: "card-presets"
    }, h(SectionTitle, {
      title: "Presets",
      caption: "prepared statements that exercise every engine route"
    }), h("div", {
      className: "preset-list"
    }, presets.length ? presets.map(preset => h("button", {
      key: preset.identifier,
      type: "button",
      className: "preset",
      disabled: running,
      onClick: () => usePreset(preset)
    }, h("span", {
      className: "preset-head"
    }, h("span", {
      className: "preset-label"
    }, preset.label), h(Badge, {
      tone: preset.expected === "exhaustion" ? "warn" : preset.expected === "symbolic_proof" ? "kind" : "pass"
    }, preset.expected.replace("_", " "))), h("code", {
      className: "preset-query"
    }, preset.query), h("span", {
      className: "preset-description"
    }, preset.description))) : h("p", {
      className: "dim"
    }, "Presets could not be loaded from the server."))), h(Card, {
      className: "card-budget"
    }, h(SectionTitle, {
      title: "Search budget",
      caption: "hard limits handed to the engine and to every worker process"
    }), h("div", {
      className: "slider-block"
    }, h("div", {
      className: "slider-head"
    }, h("span", null, "wall clock"), h("code", null, String(budget.time_seconds) + " s")), h(GlassSlider, {
      value: Number(budget.time_seconds),
      min: 2,
      max: 120,
      onChange: value => setBudget(current => Object.assign({}, current, {
        time_seconds: value
      }))
    })), h("div", {
      className: "slider-block"
    }, h("div", {
      className: "slider-head"
    }, h("span", null, "frontier visits"), h("code", null, String(budget.max_frontier_visits))), h(GlassSlider, {
      value: Number(budget.max_frontier_visits),
      min: 4,
      max: 400,
      onChange: value => setBudget(current => Object.assign({}, current, {
        max_frontier_visits: value
      }))
    })), h("div", {
      className: "slider-block"
    }, h("div", {
      className: "slider-head"
    }, h("span", null, "worker timeout"), h("code", null, String(budget.execution_timeout_seconds) + " s")), h(GlassSlider, {
      value: Number(budget.execution_timeout_seconds),
      min: 1,
      max: 60,
      onChange: value => setBudget(current => Object.assign({}, current, {
        execution_timeout_seconds: value
      }))
    })), groupRowVisible ? h("div", {
      className: "slider-block",
      id: "max-order-row"
    }, h("div", {
      className: "slider-head"
    }, h("span", null, "group order bound"), h("code", null, String(budget.max_group_order))), h(GlassSlider, {
      value: Number(budget.max_group_order),
      min: 1,
      max: 24,
      onChange: value => setBudget(current => Object.assign({}, current, {
        max_group_order: value
      }))
    })) : null, h("div", {
      className: "toggle-block"
    }, h(Toggle, {
      label: "Auto scroll stream",
      hint: "keep the newest event visible",
      value: autoScroll,
      onChange: setAutoScroll
    }), h(Toggle, {
      label: "Show raw event payloads",
      hint: "append the JSON of every event",
      value: showRawEvents,
      onChange: setShowRawEvents
    }), h(Toggle, {
      label: "Show generated worker",
      hint: "display the exact Python worker source",
      value: showWorker,
      onChange: setShowWorker
    }))), h(Card, {
      className: "card-history"
    }, h(SectionTitle, {
      title: "History",
      caption: "the last searches of this browser",
      aside: history.length ? h("button", {
        type: "button",
        className: "ghost-button ghost-small",
        onClick: () => {
          setHistory([]);
          writeHistory([]);
        }
      }, "Clear") : null
    }), history.length ? h("ul", {
      className: "history-list"
    }, history.map(item => h("li", {
      key: item.id
    }, h("button", {
      type: "button",
      className: "history-entry",
      disabled: running,
      onClick: () => {
        setQuery(item.query);
        startSearch(item.query);
      }
    }, h("span", {
      className: "history-head"
    }, h("span", {
      className: "history-query"
    }, item.query), h(Badge, {
      tone: item.kind === "counterexample" ? "pass" : item.kind === "exhaustion" ? "warn" : "kind"
    }, item.kind)), h("span", {
      className: "history-meta"
    }, new Date(item.at).toLocaleString() + " · " + String(item.seconds) + " s · " + String(item.headline || "").slice(0, 70)))))) : h("div", {
      className: "empty-state"
    }, h("p", {
      className: "dim"
    }, "Finished searches are stored locally in this browser only.")))), h("section", {
      className: "column column-right"
    }, failure ? h("div", {
      className: "notice notice-error"
    }, h("strong", null, "Request failed"), h("span", null, failure)) : null, h(Card, {
      className: "card-formalization"
    }, h(SectionTitle, {
      title: "Live formalization",
      caption: "what the engine understood, before the search starts"
    }), h(FormTabs, {
      formalization,
      symbolicProof: formalizedResult === "symbolic_proof"
    })), h(Card, {
      className: "card-pipeline"
    }, h(SectionTitle, {
      title: "Pipeline",
      caption: "search → generate → execute → verify → critique → certify"
    }), h(PipelineStrip, {
      states: pipeline,
      activeStep
    }), h("div", {
      className: "field-grid"
    }, h(Field, {
      label: "Current lane"
    }, frontier ? frontier.lane : "n/a"), h(Field, {
      label: "Current route"
    }, frontier ? frontier.solver_route : "n/a"), h(Field, {
      label: "Exact domain"
    }, frontier ? frontier.exact_domain : "n/a"), h(Field, {
      label: "Worker digest"
    }, digestCheck.state === "idle" ? "not generated yet" : digestCheck.state + (digestCheck.digest ? " · " + digestCheck.digest.slice(0, 16) : "")))), h(Card, {
      className: "card-result"
    }, h(SectionTitle, {
      title: "Certificate",
      caption: "the exact object the engine certified"
    }), h(ResultCard, {
      result,
      running
    })), h(Card, {
      className: "card-audit"
    }, h(SectionTitle, {
      title: "Verification audit",
      caption: "each row is produced by the verification and critique layers"
    }), h(AuditList, {
      entries: result && result.audit ? result.audit : [],
      digestCheck
    })), h(Card, {
      className: "card-exports"
    }, h(SectionTitle, {
      title: "Exports",
      caption: "reproduce the certificate outside the browser"
    }), h(ExportToolbar, {
      result,
      onToast: setToast
    })), showWorker && workerSource ? h(Card, {
      className: "card-worker"
    }, h(SectionTitle, {
      title: "Generated worker",
      caption: "the isolated Python process that produced the candidate"
    }), h("pre", {
      className: "exact-output code-block"
    }, workerSource)) : null, h(StreamLog, {
      events,
      autoScroll,
      onToggleAutoScroll: setAutoScroll,
      onClear: () => setEvents([])
    }), showRawEvents ? h(Card, {
      className: "card-raw"
    }, h(SectionTitle, {
      title: "Raw events",
      caption: "complete JSON payload of the stream"
    }), h("pre", {
      className: "exact-output code-block"
    }, events.map(entry => entry.time + " · " + entry.label).join("\n"))) : null)), h("footer", {
      className: "footer"
    }, h("span", null, "exact rational arithmetic · no floating point certificate values · no sampled claims"), h("span", null, health ? "server " + String(health.version) + " · assets " + String(health.assets) : "server status unknown")), toast ? h("div", {
      className: "toast"
    }, toast) : null));
  };
  const registerServiceWorker = () => {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", {
        scope: "/"
      }).catch(() => {});
    });
  };
  const mount = () => {
    const container = document.getElementById("root");
    if (!container) return;
    const root = ReactDOM.createRoot(container);
    root.render(h(App));
    registerServiceWorker();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();