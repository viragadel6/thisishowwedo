(function () {
  const LensSignal = class {
    constructor(initial) {
      this.current = initial;
      this.subscribers = [];
    }
    get() {
      return this.current;
    }
    set(next) {
      if (next === this.current) return;
      this.current = next;
      const subs = this.subscribers.slice();
      for (let i = 0; i < subs.length; i++) {
        subs[i](next);
      }
    }
    on(event, callback) {
      this.subscribers.push(callback);
      return () => {
        const idx = this.subscribers.indexOf(callback);
        if (idx !== -1) this.subscribers.splice(idx, 1);
      };
    }
  };
  const isGlassMotionValue = val => typeof val === "object" && val !== null && "get" in val && "on" in val;
  const readGlassValue = val => isGlassMotionValue(val) ? val.get() : val;
  const glassValue = initial => new LensSignal(initial);
  const deriveGlass = (deps, compute) => {
    const derived = glassValue(compute());
    const recompute = () => derived.set(compute());
    for (let i = 0; i < deps.length; i++) {
      deps[i].on("change", recompute);
    }
    return derived;
  };
  const cubicBezier = (x1, y1, x2, y2) => {
    const cx = 3 * x1;
    const bx = 3 * (x2 - x1) - cx;
    const ax = 1 - cx - bx;
    const cy = 3 * y1;
    const by = 3 * (y2 - y1) - cy;
    const ay = 1 - cy - by;
    const curveX = t => ((ax * t + bx) * t + cx) * t;
    const curveY = t => ((ay * t + by) * t + cy) * t;
    const slopeX = t => (3 * ax * t + 2 * bx) * t + cx;
    const solveForT = x => {
      let t = x;
      for (let i = 0; i < 8; i++) {
        const off = curveX(t) - x;
        if (Math.abs(off) < 1e-6) return t;
        const s = slopeX(t);
        if (Math.abs(s) < 1e-6) break;
        t -= off / s;
      }
      let lo = 0,
        hi = 1;
      t = x;
      while (lo < hi) {
        const sx = curveX(t);
        if (Math.abs(sx - x) < 1e-6) break;
        if (sx < x) lo = t;else hi = t;
        if (hi - lo < 1e-7) break;
        t = (lo + hi) / 2;
      }
      return t;
    };
    return x => x <= 0 ? 0 : x >= 1 ? 1 : curveY(solveForT(x));
  };
  const glassEase = cubicBezier(0.34, 1.36, 0.42, 1);
  const inFlightTweens = new WeakMap();
  const animateGlassValue = (value, to, {
    duration = 0.3,
    ease = glassEase,
    onComplete
  } = {}) => {
    const active = inFlightTweens.get(value);
    if (active) active.stop();
    const from = value.get();
    if (from === to || duration <= 0) {
      value.set(to);
      if (onComplete) onComplete();
      return {
        stop() {}
      };
    }
    const durMs = duration * 1000;
    let frame = 0;
    let startedAt = 0;
    const advance = now => {
      if (startedAt === 0) startedAt = now;
      const progress = (now - startedAt) / durMs;
      if (progress >= 1) {
        value.set(to);
        inFlightTweens.delete(value);
        if (onComplete) onComplete();
        return;
      }
      value.set(from + (to - from) * ease(progress));
      frame = requestAnimationFrame(advance);
    };
    frame = requestAnimationFrame(advance);
    const handle = {
      stop() {
        cancelAnimationFrame(frame);
        inFlightTweens.delete(value);
      }
    };
    inFlightTweens.set(value, handle);
    return handle;
  };
  const DEFAULT_LENS_PARAMS = {
    lensW: 95,
    lensH: 95,
    borderRadius: 95,
    mapSize: 512,
    clipToShape: true,
    softEdge: true,
    strength: 0.06,
    depth: 0.65,
    curvature: 0.6,
    splay: 0,
    dispersion: 0.5,
    bend: 0,
    bendWidth: 0.16,
    frost: 0.5,
    brightness: 0.1,
    specular: 1,
    sheenAngle: 45,
    sheenDark: false,
    sheen: 0.3,
    sheenWidth: 3,
    sheenFalloff: 1.5,
    glow: 0.12,
    glowSpread: 1,
    glowFalloff: 0.5
  };
  const BLANK_MAP = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
  const DISPERSION_SPREAD = 0.22;
  const ERF_K = Math.sqrt(Math.PI);
  const erf = x => Math.tanh(ERF_K * x);
  const domeGradientMean = (radius, halfExtent) => halfExtent > 0 ? (radius - Math.sqrt(radius * radius - halfExtent * halfExtent)) / halfExtent : 0;
  const computeDomeConstants = (capDepth, halfW, halfH) => {
    const cap = Math.max(0.01, Math.min(capDepth, Math.min(halfW, halfH) - 1));
    const Rx = (halfW * halfW + cap * cap) / (2 * cap);
    const Ry = (halfH * halfH + cap * cap) / (2 * cap);
    const meanX = domeGradientMean(Rx, halfW);
    const meanY = domeGradientMean(Ry, halfH);
    return {
      Rx,
      Ry,
      scaleX: meanX > 0 ? 0.5 / meanX : 1,
      scaleY: meanY > 0 ? 0.5 / meanY : 1
    };
  };
  const domeGradient = (distance, radius, scale) => {
    const inside = Math.min(distance, radius * (1 - 1e-3));
    return inside / Math.sqrt(radius * radius - inside * inside) * scale;
  };
  const matrixForAxisScale = (x, y) => `${x} 0 0 0 ${0.5 * (1 - x)}  0 ${y} 0 0 ${0.5 * (1 - y)}  0 0 1 0 0  0 0 0 1 0`;
  const maskCache = new Map();
  const roundedRectMaskUri = (w, h, radius) => {
    const boxW = Math.max(1, Math.round(w));
    const boxH = Math.max(1, Math.round(h));
    const rad = Math.max(0, Math.min(Math.round(radius), Math.min(boxW, boxH) / 2));
    const key = `rr\u00b7${boxW}\u00b7${boxH}\u00b7${rad}`;
    const cached = maskCache.get(key);
    if (cached) return {
      uri: cached,
      key
    };
    const inset = 0.5;
    const fillW = Math.max(0, boxW - 2 * inset);
    const fillH = Math.max(0, boxH - 2 * inset);
    const corner = Math.max(0, rad - inset);
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' preserveAspectRatio='none' viewBox='0 0 ${boxW} ${boxH}'><rect fill='black' rx='${corner}' ry='${corner}' x='${inset}' y='${inset}' width='${fillW}' height='${fillH}'/></svg>`;
    const uri = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    maskCache.set(key, uri);
    return {
      uri,
      key
    };
  };
  const lensShapeMaskUri = (w, h, radius) => {
    const iw = Math.max(1, Math.round(w));
    const ih = Math.max(1, Math.round(h));
    const r = Math.max(0, Math.min(Math.round(radius), Math.floor(Math.min(iw, ih) / 2)));
    return roundedRectMaskUri(iw, ih, r);
  };
  const encodeAxis = signed => (0.5 + signed) * 255 + 0.5 | 0;
  const encodeSpec = spec => 127 * spec + 128 + 0.5 | 0;
  const createLensMapGenerator = size => {
    let canvas = null;
    let ctx = null;
    let image = null;
    let domeLut = null;
    let lutDome = -Infinity;
    let lutHalfW = -Infinity;
    let lutHalfH = -Infinity;
    let lutLen = 0;
    let lutDirty = true;
    let dome = null;
    return {
      generate(shape) {
        if (!canvas) {
          canvas = document.createElement("canvas");
          canvas.width = size;
          canvas.height = size;
          ctx = canvas.getContext("2d");
          image = ctx.createImageData(size, size);
        }
        const {
          lensHalfWidth: halfW,
          lensHalfHeight: halfH,
          borderRadius,
          depth,
          clipToShape,
          softEdge,
          sheenAngle = 45,
          glow = 0,
          glowSpread = 1,
          glowFalloff = 1.5,
          sheen = 0,
          sheenWidth = 3,
          sheenFalloff = 1.5,
          curvature = 0,
          splay = 0,
          bend = 0,
          bendWidth = 0.16
        } = shape;
        const data = image.data;
        const half = size >> 1;
        const radius = Math.min(borderRadius, Math.min(halfW, halfH));
        const minHalf = Math.min(halfW, halfH);
        const depthPx = Math.min(depth * minHalf, minHalf - 1);
        const innerHalfW = Math.max(0, halfW - depthPx);
        const innerHalfH = Math.max(0, halfH - depthPx);
        const innerRadius = Math.max(0, Math.min(borderRadius, Math.min(innerHalfW, innerHalfH)));
        const falloff = depthPx > 0 ? Math.SQRT1_2 / depthPx : 1e6;
        const hasSpecular = glow > 0 || sheen > 0;
        const angle = sheenAngle * Math.PI / 180;
        const cosA = Math.cos(angle);
        const sinA = Math.sin(angle);
        const edgeInv = sheenWidth > 0 ? 1 / sheenWidth : 0;
        const glowReachInv = 1 / Math.max(2, glowSpread * Math.min(halfW, halfH));
        const stepX = 2 * halfW / size;
        const stepY = 2 * halfH / size;
        const invW = 1 / halfW;
        const invH = 1 / halfH;
        const hasDome = curvature > 0;
        const domeCap = curvature * Math.min(halfW, halfH);
        const hasSplay = splay > 0;
        const hasEdgeRefract = bend > 0;
        const erInv = 1 / Math.max(2, bendWidth * Math.min(halfW, halfH));
        const cornerDistance = (ox, oy) => ox > 0 || oy > 0 ? Math.sqrt(ox * ox + oy * oy) : 0;
        if (hasDome) {
          if (!dome || Math.abs(domeCap - lutDome) > 0.5 || Math.abs(halfW - lutHalfW) > 1 || Math.abs(halfH - lutHalfH) > 1) {
            dome = computeDomeConstants(domeCap, halfW, halfH);
            lutDome = domeCap;
            lutHalfW = halfW;
            lutHalfH = halfH;
            lutDirty = true;
          }
          if (lutLen !== half) {
            domeLut = new Float32Array(half);
            lutLen = half;
            lutDirty = true;
          }
          if (lutDirty) {
            const r2 = dome.Rx * dome.Rx;
            const rMax = dome.Rx * (1 - 1e-3);
            for (let col = 0; col < half; col++) {
              const px = -((col + 0.5) * stepX - halfW);
              const clamped = px < rMax ? px : rMax;
              domeLut[col] = clamped / Math.sqrt(r2 - clamped * clamped) * dome.scaleX;
            }
            lutDirty = false;
          }
        }
        const lut = hasDome ? domeLut : null;
        const splayHalf = 0.5 * Math.min(halfW, halfH);
        const splayInv = splayHalf > 0 ? 1 / splayHalf : 0;
        const sheenNorm = Math.SQRT1_2;
        for (let row = 0; row < half; row++) {
          const mirrorRow = size - 1 - row;
          const py = -((row + 0.5) * stepY - halfH);
          const edgeY = py - halfH + radius;
          const innerEdgeY = softEdge ? py - innerHalfH + innerRadius : 0;
          const dirYBase = hasDome && lut ? domeGradient(py, dome.Ry, dome.scaleY) : py * invH > 1 ? 1 : py * invH;
          const normY = py * invH > 1 ? 1 : py * invH;
          const splayY = hasSplay ? Math.max(0, 1 - (halfH - py) * splayInv) : 0;
          const rowBase = row * size;
          const mirrorRowBase = mirrorRow * size;
          for (let col = 0; col < half; col++) {
            const mirrorCol = size - 1 - col;
            const px = -((col + 0.5) * stepX - halfW);
            const edgeX = px - halfW + radius;
            const sdf = cornerDistance(edgeX > 0 ? edgeX : 0, edgeY > 0 ? edgeY : 0) + (edgeX > edgeY ? edgeX > 0 ? 0 : edgeX : edgeY > 0 ? 0 : edgeY) - radius;
            const i00 = (rowBase + col) * 4;
            const i01 = (rowBase + mirrorCol) * 4;
            const i10 = (mirrorRowBase + col) * 4;
            const i11 = (mirrorRowBase + mirrorCol) * 4;
            if (clipToShape && sdf >= 0) {
              for (const idx of [i00, i01, i10, i11]) {
                data[idx] = 128;
                data[idx + 1] = 128;
                data[idx + 2] = 128;
                data[idx + 3] = 255;
              }
              continue;
            }
            let dirX = lut ? lut[col] : px * invW > 1 ? 1 : px * invW;
            let dirY = dirYBase;
            if (hasSplay) {
              const yAtt = splayY * splay;
              const xAtt = Math.max(0, 1 - (halfW - px) * splayInv) * splay;
              if (yAtt > 0.001 || xAtt > 0.001) {
                const prevX = dirX;
                const prevY = dirY;
                dirX = prevX * (1 - yAtt);
                dirY = prevY * (1 - xAtt);
                const prevLen = Math.sqrt(prevX * prevX + prevY * prevY);
                const nextLen = Math.sqrt(dirX * dirX + dirY * dirY);
                if (nextLen > 0.001) {
                  const restore = prevLen / nextLen;
                  dirX *= restore;
                  dirY *= restore;
                }
              }
            }
            let edgeOpacity = 1;
            if (softEdge) {
              const ix = px - innerHalfW + innerRadius;
              const innerSdf = cornerDistance(ix > 0 ? ix : 0, innerEdgeY > 0 ? innerEdgeY : 0) + (ix > innerEdgeY ? ix > 0 ? 0 : ix : innerEdgeY > 0 ? 0 : innerEdgeY) - innerRadius;
              edgeOpacity = 0.5 * (1 + erf(innerSdf * falloff));
            }
            let dx = 0.5 * dirX * edgeOpacity;
            let dy = 0.5 * dirY * edgeOpacity;
            if (hasEdgeRefract) {
              const s = sdf < 0 ? Math.max(0, 1 + sdf * erInv) : 0;
              if (s > 0) {
                const len = Math.sqrt(dirX * dirX + dirY * dirY);
                if (len > 1e-4) {
                  const m = 6.75 * s * s * (1 - s);
                  const a = 0.5 * bend * m * edgeOpacity / len;
                  dx += dirX * a;
                  dy += dirY * a;
                }
              }
            }
            let specMain = 0;
            let specCross = 0;
            if (hasSpecular) {
              const normX = px * invW > 1 ? 1 : px * invW;
              const axisMain = Math.min(1, Math.abs(normX * cosA + normY * sinA) * sheenNorm);
              const axisCross = Math.min(1, Math.abs(normX * cosA - normY * sinA) * sheenNorm);
              if (sheen > 0) {
                const band = sdf < 0 ? Math.max(0, 1 + sdf * edgeInv) : 0;
                const b = sheen * Math.pow(band, sheenFalloff);
                specMain += b * (0.16 + 0.84 * Math.pow(axisMain, 1.6));
                specCross += b * (0.16 + 0.84 * Math.pow(axisCross, 1.6));
              }
              if (glow > 0) {
                const reach = sdf < 0 ? Math.min(1, -sdf * glowReachInv) : 1;
                const t = 1 - reach;
                const g = glow * Math.pow(t * t * (3 - 2 * t), glowFalloff) * edgeOpacity;
                specMain += g * (0.6 + 0.4 * axisMain);
                specCross += g * (0.6 + 0.4 * axisCross);
              }
              if (specMain > 1) specMain = 1;else if (specMain < -1) specMain = -1;
              if (specCross > 1) specCross = 1;else if (specCross < -1) specCross = -1;
            }
            const rPos = encodeAxis(dx);
            const rNeg = encodeAxis(-dx);
            const gPos = encodeAxis(dy);
            const gNeg = encodeAxis(-dy);
            const bMain = encodeSpec(specMain);
            const bCross = encodeSpec(specCross);
            data[i00] = rPos;
            data[i00 + 1] = gPos;
            data[i00 + 2] = bMain;
            data[i00 + 3] = 255;
            data[i01] = rNeg;
            data[i01 + 1] = gPos;
            data[i01 + 2] = bCross;
            data[i01 + 3] = 255;
            data[i10] = rPos;
            data[i10 + 1] = gNeg;
            data[i10 + 2] = bCross;
            data[i10 + 3] = 255;
            data[i11] = rNeg;
            data[i11 + 1] = gNeg;
            data[i11 + 2] = bMain;
            data[i11 + 3] = 255;
          }
        }
        ctx.putImageData(image, 0, 0);
        return canvas.toDataURL();
      },
      dispose() {
        if (canvas) {
          canvas.width = 0;
          canvas.height = 0;
          canvas = null;
        }
        ctx = null;
        image = null;
        domeLut = null;
        dome = null;
        lutDome = -Infinity;
        lutHalfW = -Infinity;
        lutHalfH = -Infinity;
        lutLen = 0;
        lutDirty = true;
      }
    };
  };
  const SPRING_STIFFNESS = 176;
  const SPRING_DAMPING = 13.6;
  const STRETCH_CEILING = 0.34;
  const SPEED_SHAPE = 0.75;
  const SPEED_DIVISOR = 84;
  const MAX_STEP = 0.033;
  const VEL_DT_MIN = 0.008;
  const VEL_DT_MAX = 0.03;
  const useLensWobble = (position, stretch, holdRef, kickRef) => {
    React.useEffect(() => {
      let frame = 0;
      let displacement = 0;
      let speedValue = 0;
      let prevStamp = 0;
      let prevPosition = position.get();
      let active = false;
      const stretchTarget = pointerSpeed => {
        const fromSpeed = Math.pow(pointerSpeed, SPEED_SHAPE) / SPEED_DIVISOR;
        const responsive = fromSpeed < STRETCH_CEILING ? fromSpeed : STRETCH_CEILING;
        const held = holdRef.current;
        const raised = responsive > held ? responsive : held;
        return raised < STRETCH_CEILING ? raised : STRETCH_CEILING;
      };
      const settled = pointerSpeed => Math.abs(displacement) < 6e-4 && Math.abs(speedValue) < 6e-3 && pointerSpeed < 6e-3 && holdRef.current === 0;
      const step = now => {
        const gap = (now - prevStamp) / 1e3;
        const dt = gap < MAX_STEP ? gap : MAX_STEP;
        prevStamp = now;
        const pos = position.get();
        const velDt = gap < VEL_DT_MIN ? VEL_DT_MIN : gap > VEL_DT_MAX ? VEL_DT_MAX : gap;
        const pointerSpeed = Math.abs((pos - prevPosition) / velDt);
        prevPosition = pos;
        const target = stretchTarget(pointerSpeed);
        const accel = SPRING_STIFFNESS * (target - displacement) - SPRING_DAMPING * speedValue;
        speedValue += accel * dt;
        displacement += speedValue * dt;
        stretch.set(displacement);
        if (settled(pointerSpeed)) {
          active = false;
          stretch.set(0);
          return;
        }
        frame = requestAnimationFrame(step);
      };
      const begin = () => {
        if (active) return;
        active = true;
        prevStamp = performance.now();
        prevPosition = position.get();
        frame = requestAnimationFrame(step);
      };
      kickRef.current = begin;
      const detach = position.on("change", begin);
      return () => {
        detach();
        cancelAnimationFrame(frame);
        kickRef.current = () => {};
      };
    }, [position, stretch, holdRef, kickRef]);
  };
  const rubberBand = (excess, limit, range) => {
    const t = excess < range ? excess / range : 1;
    return limit * t * (3 + t * (t - 3));
  };
  const GlassDiv = React.forwardRef(({
    x,
    scaleX,
    scaleY,
    style,
    children,
    ...rest
  }, forwardedRef) => {
    const nodeRef = React.useRef(null);
    React.useEffect(() => {
      const node = nodeRef.current;
      if (!node) return;
      const sources = [x, scaleX, scaleY].filter(v => v != null);
      const compose = () => {
        let transform = "";
        if (x) transform = `translateX(${x.get()}px)`;
        if (scaleX || scaleY) {
          const sx = scaleX ? scaleX.get() : 1;
          const sy = scaleY ? scaleY.get() : 1;
          transform += `${transform ? " " : ""}scale(${sx}, ${sy})`;
        }
        node.style.transform = transform;
      };
      compose();
      const detaches = sources.map(v => v.on("change", compose));
      return () => detaches.forEach(off => off());
    }, [x, scaleX, scaleY]);
    return React.createElement("div", {
      ref: node => {
        nodeRef.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);else if (forwardedRef) forwardedRef.current = node;
      },
      style: style,
      ...rest
    }, children);
  });
  const VERT = `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;
  const BLIT_FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_src;
void main() { o = texture(u_src, v_uv); }`;
  const BLUR_FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_src;
uniform vec2 u_step;
void main() {
  vec4 c = texture(u_src, v_uv) * 0.1857;
  c += (texture(u_src, v_uv + u_step)       + texture(u_src, v_uv - u_step))       * 0.1671;
  c += (texture(u_src, v_uv + 2.0 * u_step) + texture(u_src, v_uv - 2.0 * u_step)) * 0.1227;
  c += (texture(u_src, v_uv + 3.0 * u_step) + texture(u_src, v_uv - 3.0 * u_step)) * 0.0768;
  c += (texture(u_src, v_uv + 4.0 * u_step) + texture(u_src, v_uv - 4.0 * u_step)) * 0.0414;
  o = c;
}`;
  const LENS_FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_src;
uniform sampler2D u_blur;
uniform sampler2D u_disp;
uniform vec2 u_origin;
uniform vec2 u_size;
uniform vec2 u_scale;
uniform vec2 u_lenspx;
uniform float u_radiuspx;
uniform float u_dispersion;
uniform float u_sheen;
uniform float u_frost;
uniform float u_opacity;
uniform float u_brightness;

float sdRoundRect(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

vec3 frosted(vec2 p, float mixAmt) {
  vec3 raw = texture(u_src, p).rgb;
  return mixAmt > 0.0 ? mix(raw, texture(u_blur, p).rgb, mixAmt) : raw;
}

void main() {
  vec2 lensUV = (v_uv - u_origin) / u_size;
  vec2 p = (lensUV - 0.5) * u_lenspx;
  float sdf = sdRoundRect(p, u_lenspx * 0.5, min(u_radiuspx, min(u_lenspx.x, u_lenspx.y) * 0.5));
  float coverage = (1.0 - smoothstep(-1.0, 1.0, sdf)) * u_opacity;
  if (coverage <= 0.0) discard;
  vec4 d = texture(u_disp, clamp(lensUV, 0.0, 1.0));
  vec2 disp = (d.rg - 0.5) * u_scale;
  vec2 uvR = v_uv + disp * (1.0 + u_dispersion * 0.22);
  vec2 uvG = v_uv + disp * (1.0 + u_dispersion * 0.11);
  vec2 uvB = v_uv + disp;
  vec3 lensCol = vec3(frosted(uvR, u_frost).r, frosted(uvG, u_frost).g, frosted(uvB, u_frost).b);
  lensCol += u_sheen * max(0.0, d.b - 0.5);
  if (u_brightness > 0.0) lensCol = mix(lensCol, vec3(1.0), clamp(u_brightness, 0.0, 1.0));
  else if (u_brightness < 0.0) lensCol = mix(lensCol, vec3(0.0), clamp(-u_brightness, 0.0, 1.0));
  vec3 backdrop = texture(u_src, v_uv).rgb;
  o = vec4(mix(backdrop, lensCol, coverage), 1.0);
}`;
  const compileShader = (gl, type, src) => {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(sh);
      gl.deleteShader(sh);
      throw new Error(`Shader: ${log}`);
    }
    return sh;
  };
  const linkProgram = (gl, vsSrc, fsSrc) => {
    const p = gl.createProgram();
    const vs = compileShader(gl, gl.VERTEX_SHADER, vsSrc);
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, fsSrc);
    gl.attachShader(p, vs);
    gl.attachShader(p, fs);
    gl.bindAttribLocation(p, 0, "a_pos");
    gl.linkProgram(p);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      const log = gl.getProgramInfoLog(p);
      gl.deleteProgram(p);
      throw new Error(`Link: ${log}`);
    }
    return p;
  };
  const GlassWebGLRenderer = class {
    constructor(canvas) {
      const gl = canvas.getContext("webgl2", {
        premultipliedAlpha: false,
        alpha: true,
        antialias: false,
        preserveDrawingBuffer: false
      });
      if (!gl) throw new Error("WebGL2 not available");
      this.gl = gl;
      this.blit = linkProgram(gl, VERT, BLIT_FRAG);
      this.lens = linkProgram(gl, VERT, LENS_FRAG);
      this.blur = linkProgram(gl, VERT, BLUR_FRAG);
      this.quad = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const makeTex = () => {
        const t = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, t);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        return t;
      };
      this.srcTex = makeTex();
      this.dispTex = makeTex();
      this.dispCache = new Map();
      this.blurTex = [makeTex(), makeTex()];
      this.fbo = [gl.createFramebuffer(), gl.createFramebuffer()];
      this.blurW = 0;
      this.blurH = 0;
      this.srcW = 0;
      this.srcH = 0;
      this.disposed = false;
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      this.uBlitSrc = gl.getUniformLocation(this.blit, "u_src");
      this.uBlur = {
        src: gl.getUniformLocation(this.blur, "u_src"),
        step: gl.getUniformLocation(this.blur, "u_step")
      };
      this.uLens = {
        src: gl.getUniformLocation(this.lens, "u_src"),
        blur: gl.getUniformLocation(this.lens, "u_blur"),
        disp: gl.getUniformLocation(this.lens, "u_disp"),
        origin: gl.getUniformLocation(this.lens, "u_origin"),
        size: gl.getUniformLocation(this.lens, "u_size"),
        scale: gl.getUniformLocation(this.lens, "u_scale"),
        lenspx: gl.getUniformLocation(this.lens, "u_lenspx"),
        radiuspx: gl.getUniformLocation(this.lens, "u_radiuspx"),
        dispersion: gl.getUniformLocation(this.lens, "u_dispersion"),
        specular: gl.getUniformLocation(this.lens, "u_sheen"),
        frost: gl.getUniformLocation(this.lens, "u_frost"),
        opacity: gl.getUniformLocation(this.lens, "u_opacity"),
        brightness: gl.getUniformLocation(this.lens, "u_brightness")
      };
    }
    ensureBlurTargets(w, h) {
      if (w === this.blurW && h === this.blurH) return;
      const gl = this.gl;
      for (let i = 0; i < 2; i++) {
        gl.bindTexture(gl.TEXTURE_2D, this.blurTex[i]);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
        gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo[i]);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.blurTex[i], 0);
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      this.blurW = w;
      this.blurH = h;
    }
    renderFrost(blurPx) {
      const gl = this.gl;
      this.ensureBlurTargets(this.srcW, this.srcH);
      gl.useProgram(this.blur);
      gl.viewport(0, 0, this.srcW, this.srcH);
      gl.activeTexture(gl.TEXTURE0);
      gl.uniform1i(this.uBlur.src, 0);
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo[0]);
      gl.bindTexture(gl.TEXTURE_2D, this.srcTex);
      gl.uniform2f(this.uBlur.step, blurPx / this.srcW, 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo[1]);
      gl.bindTexture(gl.TEXTURE_2D, this.blurTex[0]);
      gl.uniform2f(this.uBlur.step, 0, blurPx / this.srcH);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    }
    setDisplacementMap(img) {
      if (this.disposed) return;
      const gl = this.gl;
      gl.bindTexture(gl.TEXTURE_2D, this.dispTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    }
    dispTexFor(img) {
      const gl = this.gl;
      let tex = this.dispCache.get(img);
      if (!tex) {
        tex = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        this.dispCache.set(img, tex);
      }
      return tex;
    }
    releaseDispMap(img) {
      const tex = this.dispCache.get(img);
      if (tex) {
        this.gl.deleteTexture(tex);
        this.dispCache.delete(img);
      }
    }
    resize(w, h) {
      const c = this.gl.canvas;
      if (c.width !== w || c.height !== h) {
        c.width = w;
        c.height = h;
      }
    }
    uploadSource(src, w, h) {
      const gl = this.gl;
      gl.bindTexture(gl.TEXTURE_2D, this.srcTex);
      if (w !== this.srcW || h !== this.srcH) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
        this.srcW = w;
        this.srcH = h;
      } else {
        gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, src);
      }
    }
    render(source, srcW, srcH, lenses) {
      if (this.disposed || srcW === 0 || srcH === 0) return;
      const gl = this.gl;
      this.uploadSource(source, srcW, srcH);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.disable(gl.BLEND);
      const maxBlur = lenses.reduce((mx, d) => Math.max(mx, d.blur || 0), 0);
      if (maxBlur > 0) this.renderFrost(maxBlur);
      const cw = gl.canvas.width;
      const ch = gl.canvas.height;
      gl.viewport(0, 0, cw, ch);
      gl.useProgram(this.blit);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.srcTex);
      gl.uniform1i(this.uBlitSrc, 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      gl.useProgram(this.lens);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.srcTex);
      gl.uniform1i(this.uLens.src, 0);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this.dispTex);
      gl.uniform1i(this.uLens.disp, 1);
      gl.activeTexture(gl.TEXTURE2);
      gl.bindTexture(gl.TEXTURE_2D, this.blurTex[1]);
      gl.uniform1i(this.uLens.blur, 2);
      for (let i = 0; i < lenses.length; i++) {
        const d = lenses[i];
        const opacity = d.opacity == null ? 1 : d.opacity;
        if (opacity <= 0) continue;
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, d.dispMap ? this.dispTexFor(d.dispMap) : this.dispTex);
        gl.uniform2f(this.uLens.origin, d.originX, d.originY);
        gl.uniform2f(this.uLens.size, d.sizeX, d.sizeY);
        gl.uniform2f(this.uLens.scale, d.scaleX, d.scaleY);
        gl.uniform2f(this.uLens.lenspx, d.sizeX * cw, d.sizeY * ch);
        gl.uniform1f(this.uLens.radiuspx, (d.cornerRadius == null ? 0 : d.cornerRadius) * cw);
        gl.uniform1f(this.uLens.dispersion, d.dispersion);
        gl.uniform1f(this.uLens.specular, d.specular);
        gl.uniform1f(this.uLens.frost, d.blur > 0 ? Math.min(1, d.blur / 8) : 0);
        gl.uniform1f(this.uLens.opacity, opacity);
        gl.uniform1f(this.uLens.brightness, d.brightness == null ? 0 : d.brightness);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      }
    }
    dispose() {
      if (this.disposed) return;
      this.disposed = true;
      const gl = this.gl;
      gl.deleteProgram(this.blit);
      gl.deleteProgram(this.lens);
      gl.deleteProgram(this.blur);
      gl.deleteTexture(this.srcTex);
      gl.deleteTexture(this.dispTex);
      this.dispCache.forEach(t => gl.deleteTexture(t));
      this.dispCache.clear();
      gl.deleteTexture(this.blurTex[0]);
      gl.deleteTexture(this.blurTex[1]);
      gl.deleteFramebuffer(this.fbo[0]);
      gl.deleteFramebuffer(this.fbo[1]);
      gl.deleteBuffer(this.quad);
      const lose = gl.getExtension("WEBGL_lose_context");
      if (lose) lose.loseContext();
    }
  };
  const resolveLens = spec => ({
    merged: Object.assign({}, DEFAULT_LENS_PARAMS, spec.lens),
    lensW: spec.lensW,
    lensH: spec.lensH,
    radius: spec.borderRadius,
    x: spec.x,
    y: spec.y,
    scale: spec.scale == null ? 1 : spec.scale,
    opacity: spec.opacity == null ? 1 : spec.opacity
  });
  const useLensRenderer = (outRef, containerRef, getFrame, specs, maxDpr, driveOnVideoFrames) => {
    const [failed, setFailed] = React.useState(false);
    const rendererRef = React.useRef(null);
    const generatorRef = React.useRef(null);
    const shape = specs[0];
    const state = React.useRef(specs);
    state.current = specs;
    const hasLiveGeometry = specs.some(s => isGlassMotionValue(s.x) || isGlassMotionValue(s.y) || isGlassMotionValue(s.lensW) || isGlassMotionValue(s.lensH) || s.radius != null && isGlassMotionValue(s.radius));
    React.useLayoutEffect(() => {
      const out = outRef.current;
      const container = containerRef.current;
      if (!out || !container) return;
      let renderer;
      try {
        renderer = new GlassWebGLRenderer(out);
      } catch (err) {
        setFailed(true);
        return;
      }
      rendererRef.current = renderer;
      const dpr = Math.min(window.devicePixelRatio || 1, maxDpr);
      const sync = () => {
        const w = container.clientWidth;
        const h = container.clientHeight;
        out.style.width = `${w}px`;
        out.style.height = `${h}px`;
        renderer.resize(Math.round(w * dpr), Math.round(h * dpr));
      };
      sync();
      const ro = new ResizeObserver(sync);
      ro.observe(container);
      return () => {
        ro.disconnect();
        renderer.dispose();
        rendererRef.current = null;
      };
    }, [outRef, containerRef, maxDpr]);
    const m0 = shape.merged;
    const shapeW = readGlassValue(shape.lensW);
    const shapeH = readGlassValue(shape.lensH);
    const shapeR = shape.radius != null ? readGlassValue(shape.radius) : Math.min(shapeW, shapeH);
    const shapeKey = JSON.stringify([m0.mapSize, shapeW, shapeH, shapeR, m0.depth, m0.clipToShape, m0.softEdge, m0.curvature, m0.splay, m0.glow, m0.glowSpread, m0.glowFalloff, m0.sheen, m0.sheenWidth, m0.sheenFalloff, m0.sheenAngle, m0.bend, m0.bendWidth]);
    React.useEffect(() => {
      const renderer = rendererRef.current;
      if (!renderer) return;
      if (!generatorRef.current) generatorRef.current = createLensMapGenerator(m0.mapSize);
      const url = generatorRef.current.generate({
        lensHalfWidth: shapeW,
        lensHalfHeight: shapeH,
        borderRadius: shapeR,
        depth: m0.depth,
        clipToShape: m0.clipToShape,
        softEdge: m0.softEdge,
        sheenAngle: m0.sheenAngle,
        glow: m0.glow,
        glowSpread: m0.glowSpread,
        glowFalloff: m0.glowFalloff,
        sheen: m0.sheen,
        sheenWidth: m0.sheenWidth,
        sheenFalloff: m0.sheenFalloff,
        curvature: m0.curvature,
        splay: m0.splay,
        bend: m0.bend,
        bendWidth: m0.bendWidth
      });
      let stale = false;
      const img = new Image();
      img.onload = () => {
        if (!stale && rendererRef.current) rendererRef.current.setDisplacementMap(img);
      };
      img.src = url;
      return () => {
        stale = true;
      };
    }, [shapeKey, failed]);
    const keyOf = s => {
      const m = s.merged;
      const w = readGlassValue(s.lensW);
      const h = readGlassValue(s.lensH);
      const r = s.radius != null ? readGlassValue(s.radius) : Math.min(w, h);
      return JSON.stringify([m.mapSize, w, h, r, m.depth, m.clipToShape, m.softEdge, m.curvature, m.splay, m.glow, m.glowSpread, m.glowFalloff, m.sheen, m.sheenWidth, m.sheenFalloff, m.sheenAngle, m.bend, m.bendWidth]);
    };
    const lensKeys = specs.map(keyOf);
    const lensKeysRef = React.useRef(lensKeys);
    lensKeysRef.current = lensKeys;
    const perLensMaps = React.useRef(new Map());
    const perLensKey = lensKeys.join("|");
    React.useEffect(() => {
      const gen = generatorRef.current;
      if (!gen) return;
      const live = new Set(lensKeysRef.current);
      perLensMaps.current.forEach((img, key) => {
        if (!live.has(key)) {
          perLensMaps.current.delete(key);
          if (rendererRef.current) rendererRef.current.releaseDispMap(img);
        }
      });
      const defaultKey = lensKeysRef.current[0];
      const cleanups = [];
      const want = new Set();
      specs.forEach((s, i) => {
        const key = lensKeysRef.current[i];
        if (key === defaultKey || want.has(key) || perLensMaps.current.has(key)) return;
        want.add(key);
        const m = s.merged;
        const w = readGlassValue(s.lensW);
        const h = readGlassValue(s.lensH);
        const r = s.radius != null ? readGlassValue(s.radius) : Math.min(w, h);
        const url = gen.generate({
          lensHalfWidth: w,
          lensHalfHeight: h,
          borderRadius: r,
          depth: m.depth,
          clipToShape: m.clipToShape,
          softEdge: m.softEdge,
          sheenAngle: m.sheenAngle,
          glow: m.glow,
          glowSpread: m.glowSpread,
          glowFalloff: m.glowFalloff,
          sheen: m.sheen,
          sheenWidth: m.sheenWidth,
          sheenFalloff: m.sheenFalloff,
          curvature: m.curvature,
          splay: m.splay,
          bend: m.bend,
          bendWidth: m.bendWidth
        });
        let stale = false;
        const img = new Image();
        img.onload = () => {
          if (!stale) perLensMaps.current.set(key, img);
        };
        img.src = url;
        cleanups.push(() => {
          stale = true;
        });
      });
      return () => cleanups.forEach(c => c());
    }, [perLensKey, failed]);
    React.useEffect(() => () => {
      if (generatorRef.current) {
        generatorRef.current.dispose();
        generatorRef.current = null;
      }
    }, []);
    React.useEffect(() => {
      if (failed) return;
      let raf = 0;
      let vfc = 0;
      const v = driveOnVideoFrames;
      const useVfc = Boolean(v) && !hasLiveGeometry && typeof v.requestVideoFrameCallback === "function";
      const draw = () => {
        const renderer = rendererRef.current;
        const container = containerRef.current;
        if (!renderer || !container) return;
        const frame = getFrame();
        if (frame && frame.w > 0 && frame.h > 0) {
          const cw = container.clientWidth;
          const ch = container.clientHeight;
          const surfNorm = Math.sqrt((cw * cw + ch * ch) / 2);
          const keys = lensKeysRef.current;
          const descs = state.current.map((s, i) => {
            const lw = readGlassValue(s.lensW);
            const lh = readGlassValue(s.lensH);
            const rad = s.radius != null ? readGlassValue(s.radius) : Math.min(lw, lh);
            const sx = readGlassValue(s.x);
            const sy = readGlassValue(s.y);
            const ehw = lw * s.scale;
            const ehh = lh * s.scale;
            const ownsShape = i > 0 && keys[i] !== keys[0];
            const ownMap = ownsShape ? perLensMaps.current.get(keys[i]) : undefined;
            const flat = ownsShape && !ownMap;
            return {
              originX: (sx * cw - ehw) / cw,
              originY: 1 - (sy * ch + ehh) / ch,
              sizeX: 2 * ehw / cw,
              sizeY: 2 * ehh / ch,
              scaleX: flat ? 0 : (s.merged.scaleX == null ? s.merged.strength : s.merged.scaleX) * surfNorm / cw,
              scaleY: flat ? 0 : (s.merged.scaleY == null ? s.merged.strength : s.merged.scaleY) * surfNorm / ch,
              dispersion: s.merged.dispersion,
              specular: s.merged.specular,
              blur: s.merged.frost,
              cornerRadius: rad * s.scale / cw,
              opacity: s.opacity,
              brightness: s.merged.brightness,
              dispMap: ownMap
            };
          });
          renderer.render(frame.source, frame.w, frame.h, descs);
        }
        if (useVfc) vfc = v.requestVideoFrameCallback(draw);else raf = requestAnimationFrame(draw);
      };
      if (useVfc) vfc = v.requestVideoFrameCallback(draw);else raf = requestAnimationFrame(draw);
      return () => {
        cancelAnimationFrame(raf);
        if (useVfc && vfc && v && v.cancelVideoFrameCallback) v.cancelVideoFrameCallback(vfc);
      };
    }, [failed, getFrame, containerRef, driveOnVideoFrames, hasLiveGeometry]);
    return failed;
  };
  const GlassSurface = ({
    src,
    draw,
    poster,
    loop = true,
    muted = true,
    autoPlay = true,
    crossOrigin,
    paused,
    videoRef: externalVideoRef,
    lenses,
    width,
    height,
    lens,
    lensW = 90,
    lensH = 90,
    borderRadius,
    x = 0.5,
    y = 0.5,
    maxDpr = 1.5,
    className,
    style,
    children
  }) => {
    const isVideo = src != null;
    const containerRef = React.useRef(null);
    const outRef = React.useRef(null);
    const videoRef = React.useRef(null);
    const [video, setVideo] = React.useState(null);
    const setVideoEl = React.useCallback(el => {
      videoRef.current = el;
      if (typeof externalVideoRef === "function") externalVideoRef(el);else if (externalVideoRef) externalVideoRef.current = el;
    }, [externalVideoRef]);
    const srcRef = React.useRef(null);
    const drawRef = React.useRef(draw);
    drawRef.current = draw;
    const startRef = React.useRef(0);
    if (!isVideo && !srcRef.current && typeof document !== "undefined") {
      srcRef.current = document.createElement("canvas");
    }
    const specs = (lenses && lenses.length ? lenses.map(l => ({
      lens: l.optics ? Object.assign({}, lens, l.optics) : lens,
      lensW: l.w / 2,
      lensH: l.h / 2,
      borderRadius: l.radius,
      x: l.x,
      y: l.y,
      scale: l.scale,
      opacity: l.opacity
    })) : [{
      lens,
      lensW,
      lensH,
      borderRadius,
      x,
      y
    }]).map(resolveLens);
    React.useEffect(() => {
      if (isVideo) setVideo(videoRef.current);
    }, [isVideo]);
    React.useEffect(() => {
      const v = videoRef.current;
      if (!isVideo || !v || paused === undefined) return;
      if (paused) v.pause();else void v.play().catch(() => {});
    }, [isVideo, paused]);
    const getFrame = React.useCallback(() => {
      if (isVideo) {
        const v = videoRef.current;
        if (!v || v.readyState < 2) return null;
        return {
          source: v,
          w: v.videoWidth,
          h: v.videoHeight
        };
      }
      const c = srcRef.current;
      const container = containerRef.current;
      if (!c || !container || !drawRef.current) return null;
      const w = width == null ? Math.round(container.clientWidth) : width;
      const h = height == null ? Math.round(container.clientHeight) : height;
      if (w === 0 || h === 0) return null;
      if (c.width !== w || c.height !== h) {
        c.width = w;
        c.height = h;
      }
      const ctx = c.getContext("2d");
      if (!ctx) return null;
      if (startRef.current === 0) startRef.current = performance.now();
      drawRef.current(ctx, performance.now() - startRef.current);
      return {
        source: c,
        w,
        h
      };
    }, [isVideo, width, height]);
    const failed = useLensRenderer(outRef, containerRef, getFrame, specs, maxDpr, isVideo ? video : null);
    React.useEffect(() => {
      const container = containerRef.current;
      const source = srcRef.current;
      if (!container || !source || isVideo) return undefined;
      if (source.parentNode !== container) container.insertBefore(source, container.firstChild);
      return () => {
        if (source.parentNode === container) container.removeChild(source);
      };
    }, [isVideo]);
    React.useEffect(() => {
      const source = srcRef.current;
      if (!source || isVideo) return;
      source.style.display = failed ? "block" : "none";
    }, [failed, isVideo]);
    return React.createElement("div", {
      ref: containerRef,
      className: className,
      style: Object.assign({
        position: "relative",
        overflow: "hidden"
      }, style)
    }, isVideo && React.createElement("video", {
      ref: setVideoEl,
      src: src,
      poster: poster,
      loop: loop,
      muted: muted,
      autoPlay: autoPlay,
      playsInline: true,
      crossOrigin: crossOrigin,
      style: {
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        objectFit: "cover",
        visibility: failed ? "visible" : "hidden"
      }
    }), React.createElement("canvas", {
      ref: outRef,
      style: {
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        display: failed ? "none" : "block"
      }
    }), isVideo && failed && React.createElement("div", {
      style: {
        position: "absolute",
        left: 12,
        bottom: 12,
        color: "#94a3b8",
        fontSize: 12,
        letterSpacing: "0.02em"
      }
    }, "WebGL2 unavailable - plain video without refraction"), children != null && React.createElement("div", {
      style: {
        position: "absolute",
        inset: 0
      }
    }, children));
  };
  const MATERIAL_OPTICS = {
    strength: 0.05,
    depth: 0.5,
    curvature: 0.3,
    bend: 0.45,
    bendWidth: 0.16,
    dispersion: 0.32,
    frost: 6,
    saturate: 1.15,
    sheen: 0.32,
    sheenWidth: 3,
    sheenFalloff: 1.5,
    glow: 0.1,
    glowSpread: 1,
    glowFalloff: 0.5,
    specular: 1,
    sheenAngle: 45,
    brightness: 0
  };
  const useSupportsBackdropUrl = () => {
    const [ok, setOk] = React.useState(false);
    React.useEffect(() => {
      if (typeof navigator === "undefined") return;
      const ua = navigator.userAgent;
      const hasUAData = navigator.userAgentData != null;
      const isBlink = hasUAData || /\b(?:Chrome|Chromium|Edg)\//.test(ua) && !/\b(?:CriOS|EdgiOS|FxiOS|OPiOS)\b/.test(ua) && !/iPhone|iPad|iPod/.test(ua);
      setOk(isBlink);
    }, []);
    return ok;
  };
  const MaterialFilterContents = ({
    dispScale,
    dispersion,
    specular,
    hasSpecular,
    mapMatrix,
    width,
    height,
    mapUrl,
    feImageRef
  }) => {
    const mapInput = mapMatrix ? "scaledMap" : "map";
    return React.createElement(React.Fragment, null, React.createElement("feFlood", {
      floodColor: "rgb(128,128,128)",
      floodOpacity: "1",
      result: "mapBg"
    }), React.createElement("feImage", {
      ref: feImageRef,
      href: mapUrl || undefined,
      x: 0,
      y: 0,
      width: width,
      height: height,
      preserveAspectRatio: "none",
      result: "rawMap"
    }), React.createElement("feComposite", {
      in: "rawMap",
      in2: "mapBg",
      operator: "over",
      result: "map"
    }), mapMatrix && React.createElement("feColorMatrix", {
      in: "map",
      type: "matrix",
      values: mapMatrix,
      result: "scaledMap"
    }), dispersion > 0 ? React.createElement(React.Fragment, null, React.createElement("feDisplacementMap", {
      in: "SourceGraphic",
      in2: mapInput,
      scale: dispScale * (1 + DISPERSION_SPREAD * dispersion),
      xChannelSelector: "R",
      yChannelSelector: "G"
    }), React.createElement("feColorMatrix", {
      type: "matrix",
      values: "1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0",
      result: "refractR"
    }), React.createElement("feDisplacementMap", {
      in: "SourceGraphic",
      in2: mapInput,
      scale: dispScale * (1 + DISPERSION_SPREAD * 0.5 * dispersion),
      xChannelSelector: "R",
      yChannelSelector: "G"
    }), React.createElement("feColorMatrix", {
      type: "matrix",
      values: "0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0",
      result: "refractG"
    }), React.createElement("feDisplacementMap", {
      in: "SourceGraphic",
      in2: mapInput,
      scale: dispScale,
      xChannelSelector: "R",
      yChannelSelector: "G"
    }), React.createElement("feColorMatrix", {
      type: "matrix",
      values: "0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0",
      result: "refractB"
    }), React.createElement("feComposite", {
      in: "refractR",
      in2: "refractG",
      operator: "arithmetic",
      k1: "0",
      k2: "1",
      k3: "1",
      k4: "0",
      result: "refractRG"
    }), React.createElement("feComposite", {
      in: "refractRG",
      in2: "refractB",
      operator: "arithmetic",
      k1: "0",
      k2: "1",
      k3: "1",
      k4: "0",
      result: "lensOut"
    })) : React.createElement("feDisplacementMap", {
      in: "SourceGraphic",
      in2: mapInput,
      scale: dispScale,
      xChannelSelector: "R",
      yChannelSelector: "G",
      result: "lensOut"
    }), hasSpecular && React.createElement(React.Fragment, null, React.createElement("feColorMatrix", {
      in: "map",
      type: "matrix",
      values: `0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 1 0 ${-128 / 255}`,
      result: "sheenMask"
    }), React.createElement("feComposite", {
      in: "sheenMask",
      in2: "lensOut",
      operator: "arithmetic",
      k1: "0",
      k2: specular,
      k3: "1",
      k4: "0"
    })));
  };
  const num = v => v == null ? undefined : isGlassMotionValue(v) ? readGlassValue(v) : v;
  const GlassMaterial = React.forwardRef(({
    children,
    optics,
    radius,
    width,
    height,
    className,
    style,
    ...rest
  }, forwardedRef) => {
    const supportsUrl = useSupportsBackdropUrl();
    const merged = React.useMemo(() => Object.assign({}, DEFAULT_LENS_PARAMS, MATERIAL_OPTICS, optics), [optics]);
    const baseId = React.useId().replace(/:/g, "");
    const wrapRef = React.useRef(null);
    const filterRef = React.useRef(null);
    const feImageRef = React.useRef(null);
    const generatorRef = React.useRef(null);
    const mapUrlRef = React.useRef("");
    const versionRef = React.useRef(0);
    const [box, setBox] = React.useState({
      w: 0,
      h: 0,
      r: 0,
      appliedR: undefined
    });
    const [needsRelative, setNeedsRelative] = React.useState(false);
    const sized = box.w > 0 && box.h > 0;
    const explicitR = num(radius);
    const explicitW = num(width);
    const explicitH = num(height);
    const styleHasRadius = style && style.borderRadius != null;
    const adoptedRef = React.useRef(false);
    React.useLayoutEffect(() => {
      adoptedRef.current = false;
    }, [explicitR, styleHasRadius, className]);
    React.useLayoutEffect(() => {
      const el = wrapRef.current;
      if (!el) return;
      const measure = () => {
        const rect = el.getBoundingClientRect();
        const hasCS = typeof getComputedStyle !== "undefined";
        const cs = hasCS ? getComputedStyle(el) : null;
        const own = cs ? parseFloat(cs.borderTopLeftRadius) || 0 : 0;
        if (cs) {
          const pos = cs.position;
          setNeedsRelative(prev => pos === "static" ? true : pos === "relative" ? prev : false);
        }
        let r, appliedR;
        if (explicitR != null) {
          r = explicitR;
          appliedR = explicitR;
        } else if (styleHasRadius || own > 0 && !adoptedRef.current) {
          r = own;
          appliedR = undefined;
        } else {
          let child = el.firstElementChild;
          while (child && child.hasAttribute("data-lg-layer")) {
            child = child.nextElementSibling;
          }
          const childR = child && hasCS ? parseFloat(getComputedStyle(child).borderTopLeftRadius) || 0 : 0;
          r = childR;
          appliedR = childR;
          adoptedRef.current = true;
        }
        setBox(prev => prev.w === rect.width && prev.h === rect.height && prev.r === r && prev.appliedR === appliedR ? prev : {
          w: rect.width,
          h: rect.height,
          r,
          appliedR
        });
      };
      measure();
      const ro = new ResizeObserver(measure);
      ro.observe(el);
      window.addEventListener("resize", measure);
      return () => {
        ro.disconnect();
        window.removeEventListener("resize", measure);
      };
    }, [explicitR, styleHasRadius, className]);
    const shapeKey = JSON.stringify([box.w, box.h, box.r, merged.mapSize, merged.clipToShape, merged.softEdge, merged.depth, merged.curvature, merged.splay, merged.bend, merged.bendWidth, merged.sheen, merged.sheenWidth, merged.sheenFalloff, merged.sheenAngle, merged.glow, merged.glowSpread, merged.glowFalloff]);
    const sx = merged.scaleX == null ? merged.strength : merged.scaleX;
    const sy = merged.scaleY == null ? merged.strength : merged.scaleY;
    const maxScale = Math.max(sx, sy);
    const norm = sized ? Math.sqrt((box.w * box.w + box.h * box.h) / 2) : 0;
    const dispScale = maxScale * norm;
    const margin = sized ? Math.ceil(dispScale * (merged.dispersion > 0 ? 1.2 : 1) * 0.5 + 28) : 0;
    const mapScaleX = maxScale > 0 ? sx / maxScale : 1;
    const mapScaleY = maxScale > 0 ? sy / maxScale : 1;
    const mapMatrix = mapScaleX === 1 && mapScaleY === 1 ? null : matrixForAxisScale(mapScaleX, mapScaleY);
    const hasSpecular = merged.glow > 0 || merged.sheen > 0;
    const applyBackdropFilter = React.useMemo(() => () => {
      const el = wrapRef.current;
      const filterEl = filterRef.current;
      if (!el) return;
      const frost = Math.max(0, merged.frost);
      const sat = merged.saturate == null ? 1 : merged.saturate;
      const fns = [frost > 0 ? `blur(${frost}px)` : "", sat !== 1 ? `saturate(${sat})` : ""].filter(Boolean).join(" ");
      let value = fns || "none";
      if (supportsUrl && filterEl && mapUrlRef.current) {
        versionRef.current += 1;
        filterEl.id = `lg-mat-${baseId}-v${versionRef.current}`;
        value = `${fns ? fns + " " : ""}url(#${filterEl.id})`;
      }
      el.style.backdropFilter = value;
      el.style.setProperty("-webkit-backdrop-filter", value);
    }, [merged.frost, merged.saturate, supportsUrl, baseId]);
    React.useLayoutEffect(() => {
      if (!sized) return;
      const mapSize = merged.mapSize;
      if (!generatorRef.current || generatorRef.current.size !== mapSize) {
        if (generatorRef.current) generatorRef.current.gen.dispose();
        generatorRef.current = {
          gen: createLensMapGenerator(mapSize),
          size: mapSize
        };
      }
      const url = generatorRef.current.gen.generate({
        lensHalfWidth: box.w / 2,
        lensHalfHeight: box.h / 2,
        borderRadius: box.r,
        depth: merged.depth,
        clipToShape: merged.clipToShape,
        softEdge: merged.softEdge,
        sheenAngle: merged.sheenAngle,
        glow: merged.glow,
        glowSpread: merged.glowSpread,
        glowFalloff: merged.glowFalloff,
        sheen: merged.sheen,
        sheenWidth: merged.sheenWidth,
        sheenFalloff: merged.sheenFalloff,
        curvature: merged.curvature,
        splay: merged.splay,
        bend: merged.bend,
        bendWidth: merged.bendWidth
      });
      mapUrlRef.current = url;
      if (feImageRef.current) feImageRef.current.setAttribute("href", url);
      applyBackdropFilter();
    }, [sized, shapeKey]);
    React.useEffect(() => {
      if (sized) applyBackdropFilter();
    }, [sized, applyBackdropFilter, merged.dispersion, merged.strength, merged.scaleX, merged.scaleY, merged.specular]);
    React.useEffect(() => () => {
      if (generatorRef.current) {
        generatorRef.current.gen.dispose();
        generatorRef.current = null;
      }
    }, []);
    const edgeShadow = React.useMemo(() => {
      const g = Math.max(0, Math.min(1.5, merged.specular));
      return [`inset 0 1px 0 rgba(255,255,255,${(0.55 * g).toFixed(3)})`, `inset 0 0 0 1px rgba(255,255,255,${(0.12 * g).toFixed(3)})`].join(", ");
    }, [merged.specular]);
    const userPos = style && style.position;
    const userPositioned = userPos != null && userPos !== "static" && userPos !== "unset" && userPos !== "initial";
    const position = userPositioned ? userPos : needsRelative ? "relative" : undefined;
    const brightnessLayer = merged.brightness !== 0 ? React.createElement("div", {
      "aria-hidden": true,
      "data-lg-layer": "",
      style: {
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        borderRadius: "inherit",
        background: merged.brightness > 0 ? "#fff" : "#000",
        opacity: Math.min(1, Math.abs(merged.brightness))
      }
    }) : null;
    return React.createElement("div", {
      ref: node => {
        wrapRef.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);else if (forwardedRef) forwardedRef.current = node;
      },
      "data-liquid-glass": "material",
      className: className,
      style: Object.assign({
        display: "inline-block"
      }, style, position != null ? {
        position
      } : null, explicitW != null ? {
        width: explicitW
      } : null, explicitH != null ? {
        height: explicitH
      } : null, box.appliedR != null ? {
        borderRadius: box.appliedR
      } : null),
      ...rest
    }, brightnessLayer, children, React.createElement("div", {
      "aria-hidden": true,
      "data-lg-layer": "",
      style: {
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        borderRadius: "inherit",
        boxShadow: edgeShadow
      }
    }), React.createElement("svg", {
      "aria-hidden": true,
      "data-lg-layer": "",
      width: 0,
      height: 0,
      style: {
        position: "absolute",
        width: 0,
        height: 0
      }
    }, React.createElement("defs", null, React.createElement("filter", {
      ref: filterRef,
      id: `lg-mat-${baseId}-v0`,
      filterUnits: "userSpaceOnUse",
      primitiveUnits: "userSpaceOnUse",
      colorInterpolationFilters: "sRGB",
      x: -margin,
      y: -margin,
      width: box.w + 2 * margin,
      height: box.h + 2 * margin
    }, sized && React.createElement(MaterialFilterContents, {
      dispScale: dispScale,
      dispersion: merged.dispersion,
      specular: merged.specular,
      hasSpecular: hasSpecular,
      mapMatrix: mapMatrix,
      width: box.w,
      height: box.h,
      mapUrl: mapUrlRef.current || "",
      feImageRef: feImageRef
    })))));
  });
  const useIsWebKit = () => {
    const [isWebKit, setIsWebKit] = React.useState(false);
    React.useEffect(() => {
      setIsWebKit(typeof navigator !== "undefined" && /^((?!chrome|chromium|android).)*safari/i.test(navigator.userAgent));
    }, []);
    return isWebKit;
  };
  const LensFilterContents = ({
    lens,
    mapHref,
    feImageRef,
    mapMatrixRef,
    blurStdDeviation,
    specularFromRawMap,
    brightnessInFilter,
    filterW,
    filterH,
    clipShapeRef
  }) => {
    const lensSX = lens.scaleX == null ? lens.strength : lens.scaleX;
    const lensSY = lens.scaleY == null ? lens.strength : lens.scaleY;
    const maxScale = Math.max(lensSX, lensSY);
    const dispNorm = filterW && filterH ? Math.sqrt((filterW * filterW + filterH * filterH) / 2) : 1;
    const dispScale = maxScale * dispNorm;
    const mapScaleX = maxScale > 0 ? lensSX / maxScale : 0;
    const mapScaleY = maxScale > 0 ? lensSY / maxScale : 0;
    const needsMapScale = !(mapScaleX === 1 && mapScaleY === 1);
    const mapInput = needsMapScale ? "scaledMap" : "map";
    const hasBlur = lens.frost > 0 && Boolean(blurStdDeviation);
    const sourceInput = hasBlur ? "blurred" : "SourceGraphic";
    const hasSpecular = lens.glow > 0 || lens.sheen > 0;
    const spec = lens.specular;
    const inFilterBrightness = brightnessInFilter && lens.brightness !== 0;
    const needsShape = hasBlur || inFilterBrightness;
    return React.createElement(React.Fragment, null, React.createElement("feFlood", {
      floodColor: "rgb(128,128,128)",
      floodOpacity: "1",
      result: "mapBg"
    }), React.createElement("feImage", {
      ref: feImageRef,
      "data-lens": "",
      href: mapHref,
      preserveAspectRatio: "none",
      result: "rawMap"
    }), React.createElement("feComposite", {
      in: "rawMap",
      in2: "mapBg",
      operator: "over",
      result: "map"
    }), needsMapScale && React.createElement("feColorMatrix", {
      ref: mapMatrixRef,
      in: "map",
      type: "matrix",
      values: matrixForAxisScale(mapScaleX, mapScaleY),
      result: "scaledMap"
    }), hasBlur && React.createElement("feGaussianBlur", {
      in: "SourceGraphic",
      stdDeviation: blurStdDeviation,
      result: "blurred"
    }), needsShape && React.createElement("feImage", {
      ref: clipShapeRef,
      "data-lens": "",
      href: BLANK_MAP,
      preserveAspectRatio: "none",
      result: "lensShape"
    }), lens.dispersion > 0 ? React.createElement(React.Fragment, null, React.createElement("feDisplacementMap", {
      "data-lens": "",
      in: sourceInput,
      in2: mapInput,
      scale: dispScale * (1 + DISPERSION_SPREAD * 0.5 * lens.dispersion),
      xChannelSelector: "R",
      yChannelSelector: "G"
    }), React.createElement("feColorMatrix", {
      type: "matrix",
      values: "1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0",
      result: "refractR"
    }), React.createElement("feDisplacementMap", {
      "data-lens": "",
      in: sourceInput,
      in2: mapInput,
      scale: dispScale,
      xChannelSelector: "R",
      yChannelSelector: "G"
    }), React.createElement("feColorMatrix", {
      type: "matrix",
      values: "0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0",
      result: "refractG"
    }), React.createElement("feDisplacementMap", {
      "data-lens": "",
      in: sourceInput,
      in2: mapInput,
      scale: dispScale * (1 - DISPERSION_SPREAD * 0.5 * lens.dispersion),
      xChannelSelector: "R",
      yChannelSelector: "G"
    }), React.createElement("feColorMatrix", {
      type: "matrix",
      values: "0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0",
      result: "refractB"
    }), React.createElement("feComposite", {
      in: "refractR",
      in2: "refractG",
      operator: "arithmetic",
      k1: "0",
      k2: "1",
      k3: "1",
      k4: "0",
      result: "refractRG"
    }), React.createElement("feComposite", {
      in: "refractRG",
      in2: "refractB",
      operator: "arithmetic",
      k1: "0",
      k2: "1",
      k3: "1",
      k4: "0",
      result: "lensOut"
    })) : React.createElement("feDisplacementMap", {
      "data-lens": "",
      in: sourceInput,
      in2: mapInput,
      scale: dispScale,
      xChannelSelector: "R",
      yChannelSelector: "G",
      result: "lensOut"
    }), hasSpecular && (lens.sheenDark ? React.createElement(React.Fragment, null, React.createElement("feColorMatrix", {
      in: specularFromRawMap ? "rawMap" : "map",
      type: "matrix",
      values: `0 0 ${-spec} 0 ${1 + 128 * spec / 255}  0 0 ${-spec} 0 ${1 + 128 * spec / 255}  0 0 ${-spec} 0 ${1 + 128 * spec / 255}  0 0 0 0 1`,
      result: "sheenMask"
    }), React.createElement("feComposite", {
      in: "sheenMask",
      in2: "lensOut",
      operator: "arithmetic",
      k1: "1",
      k2: "0",
      k3: "0",
      k4: "0",
      result: "lensOut"
    })) : React.createElement(React.Fragment, null, React.createElement("feColorMatrix", {
      in: specularFromRawMap ? "rawMap" : "map",
      type: "matrix",
      values: `0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 1 0 ${-128 / 255}`,
      result: "sheenMask"
    }), React.createElement("feComposite", {
      in: "sheenMask",
      in2: "lensOut",
      operator: "arithmetic",
      k1: "0",
      k2: spec,
      k3: "1",
      k4: "0",
      result: "lensOut"
    }))), inFilterBrightness && React.createElement(React.Fragment, null, React.createElement("feFlood", {
      "data-lens": "",
      floodColor: lens.brightness > 0 ? "white" : "black",
      floodOpacity: Math.abs(lens.brightness),
      result: "brightnessFlood"
    }), React.createElement("feComposite", {
      in: "brightnessFlood",
      in2: "lensShape",
      operator: "in",
      result: "brightnessVeil"
    }), React.createElement("feComposite", {
      in: "brightnessVeil",
      in2: "lensOut",
      operator: "over",
      result: "lensOut"
    })), needsShape ? React.createElement(React.Fragment, null, React.createElement("feComposite", {
      in: "lensOut",
      in2: "lensShape",
      operator: "in",
      result: "lensOut"
    }), React.createElement("feComposite", {
      in: "SourceGraphic",
      in2: "lensShape",
      operator: "out",
      result: "cutoutSrc"
    }), React.createElement("feComposite", {
      in: "lensOut",
      in2: "cutoutSrc",
      operator: "over"
    })) : React.createElement(React.Fragment, null, React.createElement("feFlood", {
      "data-lens": "",
      floodColor: "black",
      floodOpacity: "1",
      result: "lensMask"
    }), React.createElement("feComposite", {
      in: "SourceGraphic",
      in2: "lensMask",
      operator: "out",
      result: "cutoutSrc"
    }), React.createElement("feComposite", {
      in: "lensOut",
      in2: "cutoutSrc",
      operator: "over"
    })));
  };
  const GlassDOM = ({
    children,
    lens,
    x = 0.5,
    y = 0.5,
    lensW,
    lensH,
    borderRadius,
    refractionTarget,
    refractionBackground = "transparent",
    overlay,
    tintColor,
    tintOpacity,
    tintBlur,
    shadowOpacity,
    restShadowOpacity,
    edgeBias,
    depth,
    scale,
    filterResolution = 1,
    brightnessInFilter = false,
    pixelUnits = false,
    live = false,
    onLensMapChange,
    className,
    style,
    ...rest
  }) => {
    const isWebKit = useIsWebKit();
    const isWebKitRef = React.useRef(isWebKit);
    isWebKitRef.current = isWebKit;
    const brightnessInFilterRef = React.useRef(brightnessInFilter);
    brightnessInFilterRef.current = brightnessInFilter;
    const pixelUnitsRef = React.useRef(pixelUnits);
    pixelUnitsRef.current = pixelUnits;
    const liveRef = React.useRef(live);
    liveRef.current = live;
    const filterResolutionRef = React.useRef(filterResolution);
    filterResolutionRef.current = filterResolution;
    const merged = React.useMemo(() => Object.assign({}, DEFAULT_LENS_PARAMS, lens), [lens]);
    const mergedRef = React.useRef(merged);
    mergedRef.current = merged;
    const baseId = React.useId().replace(/:/g, "");
    const containerRef = React.useRef(null);
    const sourceRef = React.useRef(null);
    const refractionRef = React.useRef(null);
    const overlayClipRef = React.useRef(null);
    const brightnessRef = React.useRef(null);
    const tintRef = React.useRef(null);
    const blurRef = React.useRef(null);
    const shadowRef = React.useRef(null);
    const restShadowRef = React.useRef(null);
    const filterRef = React.useRef(null);
    const feImageRef = React.useRef(null);
    const shapeImageRef = React.useRef(null);
    const mapMatrixRef = React.useRef(null);
    const lensElsRef = React.useRef([]);
    const dispElsRef = React.useRef([]);
    const [size, setSize] = React.useState({
      w: 0,
      h: 0
    });
    const sizeRef = React.useRef(size);
    sizeRef.current = size;
    const sized = size.w > 0 && size.h > 0;
    const hasCopy = refractionTarget != null;
    const [autoBehind, setAutoBehind] = React.useState(null);
    React.useLayoutEffect(() => {
      if (!hasCopy || refractionBackground !== "transparent") {
        setAutoBehind(null);
        return;
      }
      if (typeof window === "undefined") return;
      let el = containerRef.current && containerRef.current.parentElement || null;
      let found = null;
      while (el) {
        const bg = getComputedStyle(el).backgroundColor;
        const match = bg.match(/rgba?\(([^)]+)\)/);
        const parts = match && match[1].split(",");
        const alpha = parts && parts[3] != null ? parseFloat(parts[3]) : 1;
        if (alpha > 0.95) {
          found = bg;
          break;
        }
        el = el.parentElement;
      }
      setAutoBehind(found);
    }, [hasCopy, refractionBackground]);
    const bleedFill = refractionBackground !== "transparent" ? refractionBackground : autoBehind == null ? "transparent" : autoBehind;
    const xRef = React.useRef(0.5);
    const yRef = React.useRef(0.5);
    const halfWRef = React.useRef(merged.lensW);
    const halfHRef = React.useRef(merged.lensH);
    const radiusRef = React.useRef(merged.borderRadius);
    const hasWRef = React.useRef(lensW !== undefined);
    hasWRef.current = lensW !== undefined;
    const hasHRef = React.useRef(lensH !== undefined);
    hasHRef.current = lensH !== undefined;
    const hasRRef = React.useRef(borderRadius !== undefined);
    hasRRef.current = borderRadius !== undefined;
    const autoRadiusRef = React.useRef(0);
    const depthRef = React.useRef(merged.depth);
    const scaleXRef = React.useRef(merged.scaleX == null ? merged.strength : merged.scaleX);
    const scaleYRef = React.useRef(merged.scaleY == null ? merged.strength : merged.scaleY);
    const tintOpacityRef = React.useRef(1);
    const tintBlurRef = React.useRef(0);
    const shadowOpacityRef = React.useRef(1);
    const restShadowOpacityRef = React.useRef(0);
    const edgeBiasRef = React.useRef(0.5);
    const lastLeftRef = React.useRef(NaN);
    const lastTopRef = React.useRef(NaN);
    const lastScaleRef = React.useRef(NaN);
    const zoomRef = React.useRef(1);
    const versionRef = React.useRef(0);
    const maskKeyRef = React.useRef("");
    const updateQueuedRef = React.useRef(false);
    const mapUrlRef = React.useRef(null);
    const shapeUrlRef = React.useRef(null);
    const generatorRef = React.useRef(null);
    const tintColorRef = React.useRef(tintColor);
    tintColorRef.current = tintColor;
    const onMapChangeRef = React.useRef(onLensMapChange);
    onMapChangeRef.current = onLensMapChange;
    const bleedNorm = size.w > 0 && size.h > 0 ? Math.sqrt((size.w * size.w + size.h * size.h) / 2) : 0;
    let bleedStrength = Math.max(merged.scaleX == null ? merged.strength : merged.scaleX, merged.scaleY == null ? merged.strength : merged.scaleY);
    if (bleedNorm > 0) {
      const fullLW = typeof lensW === "number" ? lensW * 2 : size.w;
      const fullLH = typeof lensH === "number" ? lensH * 2 : size.h;
      const dispFactor = 1 + DISPERSION_SPREAD * merged.dispersion;
      bleedStrength = Math.min(bleedStrength, Math.max(fullLW, fullLH) * 0.6 / (bleedNorm * dispFactor));
    }
    const bleed = pixelUnits && refractionTarget != null && size.w > 0 && size.h > 0 ? Math.ceil(bleedStrength * bleedNorm * (1 + DISPERSION_SPREAD * merged.dispersion) * 0.5 + merged.depth + 28) + 16 : 0;
    const bleedRef = React.useRef(bleed);
    bleedRef.current = bleed;
    React.useLayoutEffect(() => {
      const el = containerRef.current;
      if (!el) return;
      const measure = () => {
        const rect = el.getBoundingClientRect();
        if (!hasRRef.current && typeof getComputedStyle !== "undefined") {
          let r = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
          const child = sourceRef.current && sourceRef.current.firstElementChild;
          if (!r && child) r = parseFloat(getComputedStyle(child).borderTopLeftRadius) || 0;
          autoRadiusRef.current = r;
        }
        setSize(prev => prev.w === rect.width && prev.h === rect.height ? prev : {
          w: rect.width,
          h: rect.height
        });
      };
      measure();
      const ro = new ResizeObserver(measure);
      ro.observe(el);
      window.addEventListener("resize", measure);
      return () => {
        ro.disconnect();
        window.removeEventListener("resize", measure);
      };
    }, []);
    const updateGeometry = React.useCallback(() => {
      const container = containerRef.current;
      if (!container) return;
      let w = sizeRef.current.w;
      let h = sizeRef.current.h;
      if (!(w > 0 && h > 0)) {
        const rect = container.getBoundingClientRect();
        w = rect.width;
        h = rect.height;
      }
      if (!(w > 0 && h > 0)) return;
      const lensParams = mergedRef.current;
      const sx = scaleXRef.current;
      const sy = scaleYRef.current;
      let maxScale = Math.max(sx, sy);
      const dispersion = lensParams.dispersion;
      const halfW = hasWRef.current ? halfWRef.current : w / 2;
      const halfH = hasHRef.current ? halfHRef.current : h / 2;
      const radius = hasRRef.current ? radiusRef.current : autoRadiusRef.current;
      let cx = xRef.current * w;
      let cy = yRef.current * h;
      if (pixelUnitsRef.current && refractionRef.current) {
        cx = Math.max(halfW, Math.min(w - halfW, cx));
        cy = Math.max(halfH, Math.min(h - halfH, cy));
      }
      const left = cx - halfW;
      const top = cy - halfH;
      const fullW = 2 * halfW;
      const fullH = 2 * halfH;
      if (pixelUnitsRef.current) {
        const norm = Math.sqrt((w * w + h * h) / 2);
        const dispFactor = 1 + DISPERSION_SPREAD * dispersion;
        const maxDisp = Math.max(fullW, fullH) * 0.6;
        if (norm > 0) maxScale = Math.min(maxScale, maxDisp / (norm * dispFactor));
      }
      const fr = filterResolutionRef.current;
      const G = fr !== 1 && !isWebKitRef.current ? fr : 1;
      const GZ = isWebKitRef.current ? G * zoomRef.current : G;
      const posChanged = left !== lastLeftRef.current || top !== lastTopRef.current;
      const scaleChanged = maxScale !== lastScaleRef.current;
      lastLeftRef.current = left;
      lastTopRef.current = top;
      lastScaleRef.current = maxScale;
      if (posChanged || scaleChanged || liveRef.current) {
        const bias = edgeBiasRef.current;
        const px = pixelUnitsRef.current;
        const norm = Math.sqrt((w * w + h * h) / 2);
        const dispMax = maxScale * norm * (1 + DISPERSION_SPREAD * dispersion) * 0.5;
        const m = Math.ceil(dispMax + depthRef.current + 28);
        const bld = px && refractionRef.current ? bleedRef.current : 0;
        const lx = String(px ? (left + bld + bias) * GZ : (left + bias) / w);
        const ly = String(px ? (top + bld + bias) * GZ : (top + bias) / h);
        const lw = String(px ? Math.max(0, fullW - 2 * bias) * GZ : Math.max(0, fullW - 2 * bias) / w);
        const lh = String(px ? Math.max(0, fullH - 2 * bias) * GZ : Math.max(0, fullH - 2 * bias) / h);
        for (let i = 0; i < lensElsRef.current.length; i++) {
          const el = lensElsRef.current[i];
          el.setAttribute("x", lx);
          el.setAttribute("y", ly);
          el.setAttribute("width", lw);
          el.setAttribute("height", lh);
        }
        if (scaleChanged) {
          const dispBase = px ? maxScale * norm * GZ : maxScale;
          const scales = dispersion > 0 ? [dispBase * (1 + DISPERSION_SPREAD * 0.5 * dispersion), dispBase, dispBase * (1 - DISPERSION_SPREAD * 0.5 * dispersion)] : [dispBase];
          const dispEls = dispElsRef.current;
          for (let i = 0; i < dispEls.length; i++) {
            dispEls[i].setAttribute("scale", String(scales[i] == null ? 0 : scales[i]));
          }
        }
        const filterEl = filterRef.current;
        if (filterEl) {
          if (px) {
            filterEl.setAttribute("x", "0");
            filterEl.setAttribute("y", "0");
            if (refractionRef.current) {
              filterEl.setAttribute("width", String((left + bld + fullW + m) * GZ));
              filterEl.setAttribute("height", String((top + bld + fullH + m) * GZ));
            } else {
              filterEl.setAttribute("width", String(w * GZ));
              filterEl.setAttribute("height", String(h * GZ));
            }
          }
          versionRef.current += 1;
          filterEl.id = `lg-${baseId}-v${versionRef.current}`;
          const url = mapUrlRef.current ? `url(#${filterEl.id})` : "";
          if (refractionRef.current) {
            if (refractionRef.current.style.filter !== url) {
              refractionRef.current.style.filter = url;
            }
            refractionRef.current.style.clipPath = `inset(${Math.max(0, top + bld) * G}px ${Math.max(0, w + bld - (left + fullW)) * G}px ${Math.max(0, h + bld - (top + fullH)) * G}px ${Math.max(0, left + bld) * G}px round ${radius * G}px)`;
            if (sourceRef.current && !overlayClipRef.current) {
              sourceRef.current.style.filter = "";
            }
          } else if (sourceRef.current && sourceRef.current.style.filter !== url) {
            sourceRef.current.style.filter = url;
          }
        }
      }
      if (overlayClipRef.current) {
        overlayClipRef.current.style.clipPath = `inset(${Math.max(0, top) * G}px ${Math.max(0, w - (left + fullW)) * G}px ${Math.max(0, h - (top + fullH)) * G}px ${Math.max(0, left) * G}px round ${radius * G}px)`;
      }
      if (brightnessRef.current && !overlayClipRef.current) {
        brightnessRef.current.style.clipPath = `inset(${Math.max(0, top)}px ${Math.max(0, w - (left + fullW))}px ${Math.max(0, h - (top + fullH))}px ${Math.max(0, left)}px round ${radius}px)`;
      }
      const placeLensLayer = (el, opacity) => {
        el.style.transform = `translate(${left}px, ${top}px)`;
        el.style.width = `${fullW}px`;
        el.style.height = `${fullH}px`;
        el.style.borderRadius = `${radius}px`;
        if (opacity !== undefined) el.style.opacity = String(opacity);
      };
      if (shadowRef.current) placeLensLayer(shadowRef.current, shadowOpacityRef.current);
      if (restShadowRef.current) placeLensLayer(restShadowRef.current, restShadowOpacityRef.current);
      if (blurRef.current) {
        blurRef.current.style.transform = `translate3d(${left}px, ${top}px, 0)`;
        blurRef.current.style.width = `${fullW}px`;
        blurRef.current.style.height = `${fullH}px`;
        blurRef.current.style.borderRadius = `${radius}px`;
        const {
          uri,
          key
        } = roundedRectMaskUri(fullW, fullH, radius);
        if (maskKeyRef.current !== key) {
          const mask = `url("${uri}")`;
          blurRef.current.style.maskImage = mask;
          blurRef.current.style.setProperty("-webkit-mask-image", mask);
          blurRef.current.style.maskSize = "100% 100%";
          blurRef.current.style.setProperty("-webkit-mask-size", "100% 100%");
          maskKeyRef.current = key;
        }
      }
      if (tintRef.current) {
        placeLensLayer(tintRef.current);
        const color = tintColorRef.current == null ? "white" : tintColorRef.current;
        tintRef.current.style.background = `color-mix(in srgb, ${color} ${100 * tintOpacityRef.current}%, transparent)`;
        tintRef.current.style.opacity = "1";
        const blur = tintBlurRef.current > 0 ? `blur(${tintBlurRef.current}px)` : "none";
        tintRef.current.style.backdropFilter = blur;
        tintRef.current.style.setProperty("-webkit-backdrop-filter", blur);
      }
      if (mapMatrixRef.current) {
        const mx = maxScale > 0 ? sx / maxScale : 0;
        const my = maxScale > 0 ? sy / maxScale : 0;
        mapMatrixRef.current.setAttribute("values", matrixForAxisScale(mx, my));
      }
    }, [baseId]);
    const scheduleUpdate = React.useCallback(() => {
      if (updateQueuedRef.current) return;
      updateQueuedRef.current = true;
      queueMicrotask(() => {
        updateQueuedRef.current = false;
        updateGeometry();
      });
    }, [updateGeometry]);
    const forceGeometry = React.useCallback(() => {
      lastLeftRef.current = NaN;
      lastScaleRef.current = NaN;
      updateGeometry();
    }, [updateGeometry]);
    React.useEffect(() => {
      const readZoom = () => {
        const iw = window.innerWidth;
        const z = iw > 0 ? window.outerWidth / iw : 1;
        if (!(z > 0.2 && z < 12)) return 1;
        return Math.abs(z - 1) < 0.04 ? 1 : z;
      };
      const onResize = () => {
        const z = readZoom();
        if (Math.abs(z - zoomRef.current) > 0.002) {
          zoomRef.current = z;
          forceGeometry();
        }
      };
      onResize();
      window.addEventListener("resize", onResize);
      return () => window.removeEventListener("resize", onResize);
    }, [forceGeometry]);
    const regenerate = React.useCallback(() => {
      const mapSize = mergedRef.current.mapSize;
      if (!generatorRef.current || generatorRef.current.size !== mapSize) {
        if (generatorRef.current) generatorRef.current.gen.dispose();
        generatorRef.current = {
          gen: createLensMapGenerator(mapSize),
          size: mapSize
        };
      }
      const lensParams = mergedRef.current;
      const halfW = hasWRef.current ? halfWRef.current : sizeRef.current.w / 2;
      const halfH = hasHRef.current ? halfHRef.current : sizeRef.current.h / 2;
      const radius = hasRRef.current ? radiusRef.current : autoRadiusRef.current;
      const url = generatorRef.current.gen.generate({
        lensHalfWidth: halfW,
        lensHalfHeight: halfH,
        borderRadius: radius,
        depth: depthRef.current,
        clipToShape: lensParams.clipToShape,
        softEdge: lensParams.softEdge,
        sheenAngle: lensParams.sheenAngle,
        glow: lensParams.glow,
        glowSpread: lensParams.glowSpread,
        glowFalloff: lensParams.glowFalloff,
        sheen: lensParams.sheen,
        sheenWidth: lensParams.sheenWidth,
        sheenFalloff: lensParams.sheenFalloff,
        curvature: lensParams.curvature,
        splay: lensParams.splay,
        bend: lensParams.bend,
        bendWidth: lensParams.bendWidth
      });
      mapUrlRef.current = url;
      if (feImageRef.current) feImageRef.current.setAttribute("href", url);
      if (lensParams.frost > 0 || brightnessInFilterRef.current && lensParams.brightness !== 0) {
        const shape = lensShapeMaskUri(2 * halfW, 2 * halfH, radius);
        shapeUrlRef.current = shape.uri;
        if (shapeImageRef.current) shapeImageRef.current.setAttribute("href", shape.uri);
      }
      if (onMapChangeRef.current) onMapChangeRef.current(url);
      forceGeometry();
    }, [forceGeometry]);
    const regenerateRef = React.useRef(regenerate);
    regenerateRef.current = regenerate;
    const shapeKey = JSON.stringify([merged.mapSize, merged.clipToShape, merged.softEdge, merged.sheenAngle, merged.glow, merged.glowSpread, merged.glowFalloff, merged.sheen, merged.sheenWidth, merged.sheenFalloff, merged.curvature, merged.splay, merged.bend, merged.bendWidth, isGlassMotionValue(lensW) ? "mv" : lensW == null ? size.w / 2 || merged.lensW : lensW, isGlassMotionValue(lensH) ? "mv" : lensH == null ? size.h / 2 || merged.lensH : lensH, isGlassMotionValue(borderRadius) ? "mv" : borderRadius == null ? autoRadiusRef.current : borderRadius, isGlassMotionValue(depth) ? "mv" : depth == null ? merged.depth : depth, brightnessInFilter && merged.brightness !== 0]);
    React.useLayoutEffect(() => {
      const subs = [];
      const bind = (val, target, fallback, onChange) => {
        const handler = onChange || (() => {
          if (!liveRef.current) scheduleUpdate();
        });
        if (val === undefined) {
          target.current = fallback;
          return;
        }
        if (isGlassMotionValue(val)) {
          target.current = val.get();
          subs.push(val.on("change", next => {
            target.current = next;
            handler();
          }));
        } else {
          target.current = val;
        }
      };
      bind(x, xRef, 0.5);
      bind(y, yRef, 0.5);
      bind(lensW == null ? merged.lensW : lensW, halfWRef, merged.lensW);
      bind(lensH == null ? merged.lensH : lensH, halfHRef, merged.lensH);
      bind(borderRadius == null ? merged.borderRadius : borderRadius, radiusRef, merged.borderRadius);
      bind(depth == null ? merged.depth : depth, depthRef, merged.depth);
      bind(scale == null ? merged.scaleX == null ? merged.strength : merged.scaleX : scale, scaleXRef, merged.scaleX == null ? merged.strength : merged.scaleX);
      bind(scale == null ? merged.scaleY == null ? merged.strength : merged.scaleY : scale, scaleYRef, merged.scaleY == null ? merged.strength : merged.scaleY);
      bind(tintOpacity, tintOpacityRef, 1);
      bind(tintBlur, tintBlurRef, 0);
      bind(shadowOpacity, shadowOpacityRef, 1);
      bind(restShadowOpacity, restShadowOpacityRef, 0);
      bind(edgeBias, edgeBiasRef, 0.5);
      updateGeometry();
      return () => subs.forEach(unsub => unsub());
    }, [x, y, lensW, lensH, borderRadius, depth, scale, tintOpacity, tintBlur, shadowOpacity, restShadowOpacity, edgeBias, merged, scheduleUpdate, updateGeometry]);
    const hasDispersion = merged.dispersion > 0;
    const hasBlur = merged.frost > 0;
    const hasSpecular = merged.glow > 0 || merged.sheen > 0;
    React.useLayoutEffect(() => {
      const filterEl = filterRef.current;
      lensElsRef.current = filterEl ? Array.from(filterEl.querySelectorAll("[data-lens]")) : [];
      dispElsRef.current = filterEl ? Array.from(filterEl.querySelectorAll("feDisplacementMap")) : [];
      if (feImageRef.current && mapUrlRef.current) {
        feImageRef.current.setAttribute("href", mapUrlRef.current);
      }
      if (shapeImageRef.current && shapeUrlRef.current) {
        shapeImageRef.current.setAttribute("href", shapeUrlRef.current);
      }
      forceGeometry();
    }, [sized, hasDispersion, hasBlur, hasSpecular, merged.sheenDark, merged.scaleX, merged.scaleY, merged.strength, merged.brightness, brightnessInFilter, pixelUnits, isWebKit, refractionTarget != null, overlay != null, forceGeometry]);
    React.useLayoutEffect(() => {
      if (sized) forceGeometry();
    }, [size.w, size.h, bleed, forceGeometry]);
    React.useLayoutEffect(() => {
      if (!sized) return;
      regenerateRef.current();
    }, [sized, shapeKey]);
    React.useEffect(() => {
      const subs = [];
      let timer;
      const onChange = () => {
        clearTimeout(timer);
        timer = setTimeout(() => regenerateRef.current(), 90);
      };
      for (const val of [lensW, lensH, borderRadius, depth]) {
        if (isGlassMotionValue(val)) subs.push(val.on("change", onChange));
      }
      return () => {
        subs.forEach(unsub => unsub());
        clearTimeout(timer);
      };
    }, [lensW, lensH, borderRadius, depth]);
    React.useEffect(() => () => {
      if (generatorRef.current) {
        generatorRef.current.gen.dispose();
        generatorRef.current = null;
      }
      if (onMapChangeRef.current) onMapChangeRef.current(null);
    }, []);
    React.useEffect(() => {
      if (!live || !sized) return;
      let raf = 0;
      const loop = () => {
        raf = requestAnimationFrame(loop);
        updateGeometry();
      };
      raf = requestAnimationFrame(loop);
      return () => cancelAnimationFrame(raf);
    }, [live, sized, updateGeometry]);
    const blurG = filterResolution !== 1 && !isWebKit ? filterResolution : 1;
    const blurStdDeviation = hasBlur && sized ? pixelUnits ? `${merged.frost * blurG}` : `${merged.frost / size.w} ${merged.frost / size.h}` : undefined;
    const G = filterResolution !== 1 && !isWebKit ? filterResolution : 1;
    const superSource = G > 1 && overlay == null && refractionTarget == null && sized;
    const wrapMode = overlay == null && refractionTarget == null;
    const autoFitWidth = wrapMode && !superSource && lensW === undefined;
    const superWrap = (ref, content, outerStyle) => React.createElement("div", {
      ref: ref,
      style: Object.assign({}, outerStyle, {
        position: "absolute",
        top: 0,
        left: 0,
        width: size.w * G,
        height: size.h * G,
        transform: `scale(${1 / G})`,
        transformOrigin: "top left"
      })
    }, React.createElement("div", {
      style: {
        transform: `scale(${G})`,
        transformOrigin: "top left",
        width: size.w,
        height: size.h
      }
    }, content));
    const brightnessLayer = merged.brightness !== 0 && !brightnessInFilter ? React.createElement("div", {
      ref: brightnessRef,
      style: {
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        background: merged.brightness > 0 ? "white" : "black",
        opacity: Math.abs(merged.brightness)
      }
    }) : null;
    const shadowLayer = (ref, shadow, insetShadow) => shadow || insetShadow ? React.createElement("div", {
      ref: ref,
      style: {
        position: "absolute",
        top: 0,
        left: 0,
        pointerEvents: "none",
        willChange: "transform",
        boxSizing: "border-box",
        boxShadow: [shadow, insetShadow ? `inset ${insetShadow}` : null].filter(Boolean).join(", ")
      }
    }) : null;
    return React.createElement("div", {
      ref: containerRef,
      "data-liquid-glass": "",
      className: className,
      style: Object.assign({
        contain: "layout",
        position: "relative",
        overflow: "visible"
      }, autoFitWidth ? {
        width: "fit-content"
      } : null, superSource ? {
        minHeight: size.h
      } : null, style),
      ...rest
    }, superSource ? superWrap(sourceRef, children, {
      willChange: "filter"
    }) : overlay == null && refractionTarget == null ? React.createElement("div", {
      ref: sourceRef,
      style: autoFitWidth ? {
        willChange: "filter"
      } : {
        willChange: "filter",
        position: "relative",
        height: sized ? size.h : undefined,
        overflow: "hidden",
        contain: "paint"
      }
    }, children) : overlay == null && pixelUnits ? React.createElement("div", {
      ref: sourceRef,
      style: {
        position: "absolute",
        inset: 0,
        isolation: "isolate"
      }
    }, children) : React.createElement("div", {
      ref: overlay != null ? undefined : sourceRef,
      style: overlay != null ? undefined : {
        willChange: "filter"
      }
    }, children), refractionTarget != null && (pixelUnits ? React.createElement("div", {
      ref: refractionRef,
      style: {
        position: "absolute",
        inset: -bleed,
        pointerEvents: "none",
        willChange: "filter, clip-path",
        background: bleedFill
      }
    }, React.createElement("div", {
      style: {
        position: "absolute",
        inset: bleed
      }
    }, refractionTarget)) : G > 1 ? superWrap(refractionRef, refractionTarget, {
      pointerEvents: "none",
      willChange: "filter, clip-path",
      background: bleedFill
    }) : React.createElement("div", {
      ref: refractionRef,
      style: {
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        willChange: "filter, clip-path",
        background: bleedFill
      }
    }, refractionTarget)), overlay != null && React.createElement("div", {
      ref: overlayClipRef,
      style: {
        position: "absolute",
        inset: 0,
        pointerEvents: "none"
      }
    }, React.createElement("div", {
      ref: sourceRef,
      style: {
        willChange: "filter"
      }
    }, overlay), brightnessLayer), React.createElement("div", {
      style: {
        position: "absolute",
        inset: 0,
        pointerEvents: "none"
      }
    }, React.createElement("svg", {
      viewBox: `0 0 ${size.w} ${size.h}`,
      width: "100%",
      height: "100%",
      style: {
        display: "block"
      }
    }, React.createElement("defs", null, React.createElement("filter", {
      ref: filterRef,
      id: `lg-${baseId}-v0`,
      filterUnits: pixelUnits ? "userSpaceOnUse" : "objectBoundingBox",
      primitiveUnits: pixelUnits ? "userSpaceOnUse" : "objectBoundingBox",
      colorInterpolationFilters: "sRGB",
      x: 0,
      y: 0,
      width: pixelUnits ? size.w * G : 1,
      height: pixelUnits ? size.h * G : 1
    }, sized && React.createElement(LensFilterContents, {
      lens: Object.assign({}, merged, {
        scaleX: scale !== undefined ? readGlassValue(scale) : merged.scaleX == null ? merged.strength : merged.scaleX,
        scaleY: scale !== undefined ? readGlassValue(scale) : merged.scaleY == null ? merged.strength : merged.scaleY
      }),
      mapHref: BLANK_MAP,
      feImageRef: feImageRef,
      mapMatrixRef: mapMatrixRef,
      blurStdDeviation: blurStdDeviation,
      specularFromRawMap: isWebKit,
      brightnessInFilter: brightnessInFilter,
      filterW: pixelUnits ? size.w * G : undefined,
      filterH: pixelUnits ? size.h * G : undefined,
      clipShapeRef: shapeImageRef
    })))), overlay == null && brightnessLayer, tintColor !== undefined && React.createElement("div", {
      ref: tintRef,
      style: {
        position: "absolute",
        top: 0,
        left: 0,
        pointerEvents: "none",
        overflow: "hidden",
        willChange: "transform"
      }
    })), hasBlur && children == null && refractionTarget == null && overlay == null && React.createElement("div", {
      ref: blurRef,
      style: {
        position: "absolute",
        top: 0,
        left: 0,
        pointerEvents: "none",
        willChange: "backdrop-filter, transform",
        backdropFilter: `blur(${merged.frost}px)`,
        WebkitBackdropFilter: `blur(${merged.frost}px)`
      }
    }), shadowLayer(shadowRef, merged.edgeShadow, merged.edgeInsetShadow), shadowLayer(restShadowRef, merged.restEdgeShadow, merged.restEdgeInsetShadow));
  };
  const useHalf = v => React.useMemo(() => v == null ? undefined : isGlassMotionValue(v) ? deriveGlass([v], () => v.get() / 2) : v / 2, [v]);
  const Glass = props => {
    const {
      children,
      width,
      height,
      size,
      radius,
      center,
      optics,
      refract,
      behind,
      src,
      draw,
      lenses,
      videoRef,
      paused,
      poster,
      loop,
      muted,
      autoPlay,
      crossOrigin,
      maxDpr,
      unstable_lens,
      ...restProps
    } = props;
    const rest = Object.assign({}, restProps, unstable_lens == null ? null : unstable_lens);
    const cx = center && center.x;
    const cy = center && center.y;
    const pair = Array.isArray(size) ? size : size != null ? [size, size] : [undefined, undefined];
    const sw = pair[0];
    const sh = pair[1];
    const lensW = useHalf(width == null ? sw : width);
    const lensH = useHalf(height == null ? sh : height);
    if (src != null || draw != null) {
      return React.createElement(GlassSurface, {
        src: src,
        draw: draw,
        lens: optics,
        lenses: lenses,
        videoRef: videoRef,
        paused: paused,
        poster: poster,
        loop: loop,
        muted: muted,
        autoPlay: autoPlay,
        crossOrigin: crossOrigin,
        maxDpr: maxDpr,
        lensW: lensW,
        lensH: lensH,
        borderRadius: radius,
        x: cx,
        y: cy,
        className: props.className,
        style: props.style
      }, children);
    }
    const {
      overlay,
      tintColor,
      tintOpacity,
      tintBlur,
      shadowOpacity,
      restShadowOpacity,
      edgeBias,
      brightnessInFilter,
      depth,
      scale,
      filterResolution,
      pixelUnits,
      live,
      onLensMapChange,
      ...htmlRest
    } = rest;
    const animatedGeometry = isGlassMotionValue(width) || isGlassMotionValue(height) || isGlassMotionValue(radius) || isGlassMotionValue(sw) || isGlassMotionValue(sh) || isGlassMotionValue(cx) || isGlassMotionValue(cy);
    const isMaterial = children != null && refract == null && src == null && draw == null && lenses == null && overlay == null && !pixelUnits && tintColor == null && tintOpacity == null && tintBlur == null && shadowOpacity == null && restShadowOpacity == null && edgeBias == null && !brightnessInFilter && filterResolution == null && !live && depth == null && scale == null && onLensMapChange == null && cx == null && cy == null && !animatedGeometry;
    if (isMaterial) {
      return React.createElement(GlassMaterial, {
        ...htmlRest,
        optics: optics,
        radius: radius,
        width: width == null ? sw : width,
        height: height == null ? sh : height
      }, children);
    }
    return React.createElement(GlassDOM, {
      ...rest,
      lensW: lensW,
      lensH: lensH,
      borderRadius: radius,
      x: cx,
      y: cy,
      lens: optics,
      refractionTarget: refract,
      refractionBackground: behind
    }, children);
  };
  const GlassSwitch = ({
    value,
    onChange
  }) => {
    const posX = React.useMemo(() => glassValue(value ? 26 : 2), []);
    const stretch = React.useMemo(() => glassValue(0), []);
    const scaleX = React.useMemo(() => deriveGlass([stretch], () => 1 + stretch.get() * 0.4), [stretch]);
    const scaleY = React.useMemo(() => deriveGlass([stretch], () => 1 - stretch.get() * 0.2), [stretch]);
    const holdRef = React.useRef(0);
    const kickRef = React.useRef(() => {});
    useLensWobble(posX, stretch, holdRef, kickRef);
    React.useEffect(() => {
      animateGlassValue(posX, value ? 26 : 2, {
        duration: 0.28,
        ease: glassEase
      });
    }, [value, posX]);
    return React.createElement(GlassMaterial, {
      optics: MATERIAL_OPTICS,
      onClick: () => onChange(!value),
      role: "switch",
      "aria-checked": value,
      tabIndex: 0,
      onKeyDown: e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onChange(!value);
        }
      },
      style: {
        width: 58,
        height: 32,
        borderRadius: 16,
        background: value ? "rgba(0, 122, 255, 0.45)" : "rgba(255, 255, 255, 0.12)",
        border: "1px solid rgba(255, 255, 255, 0.22)",
        boxShadow: "inset 0 1px 2px rgba(0, 0, 0, 0.3)",
        position: "relative",
        cursor: "pointer",
        display: "flex",
        alignItems: "center"
      }
    }, React.createElement(GlassDiv, {
      x: posX,
      scaleX: scaleX,
      scaleY: scaleY,
      style: {
        width: 26,
        height: 26,
        borderRadius: 13,
        background: "rgba(255, 255, 255, 0.95)",
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.35), inset 0 1px 0 #fff",
        position: "absolute",
        top: 2,
        left: 0
      }
    }));
  };
  const GlassSlider = ({
    value,
    onChange,
    min = 0,
    max = 100
  }) => {
    const trackRef = React.useRef(null);
    const [dragging, setDragging] = React.useState(false);
    const posX = React.useMemo(() => glassValue(0), []);
    const updatePos = clientX => {
      if (!trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      const trackW = rect.width - 28;
      const rawX = clientX - rect.left - 14;
      let clampedX = Math.max(0, Math.min(trackW, rawX));
      if (rawX < 0) clampedX = rubberBand(-rawX, 12, 40) * -1;else if (rawX > trackW) clampedX = trackW + rubberBand(rawX - trackW, 12, 40);
      posX.set(clampedX);
      const norm = Math.max(0, Math.min(1, rawX / trackW));
      onChange(Math.round(min + norm * (max - min)));
    };
    React.useEffect(() => {
      if (!trackRef.current) return;
      const trackW = trackRef.current.clientWidth - 28;
      const targetX = (value - min) / (max - min) * trackW;
      posX.set(targetX);
    }, [value, min, max, posX]);
    return React.createElement(GlassMaterial, {
      ref: trackRef,
      optics: MATERIAL_OPTICS,
      role: "slider",
      "aria-valuemin": min,
      "aria-valuemax": max,
      "aria-valuenow": value,
      tabIndex: 0,
      onKeyDown: e => {
        const step = e.shiftKey ? Math.max(1, Math.round((max - min) / 10)) : 1;
        if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
          e.preventDefault();
          onChange(Math.max(min, value - step));
        } else if (e.key === "ArrowRight" || e.key === "ArrowUp") {
          e.preventDefault();
          onChange(Math.min(max, value + step));
        } else if (e.key === "Home") {
          e.preventDefault();
          onChange(min);
        } else if (e.key === "End") {
          e.preventDefault();
          onChange(max);
        }
      },
      onPointerDown: e => {
        setDragging(true);
        e.currentTarget.setPointerCapture(e.pointerId);
        updatePos(e.clientX);
      },
      onPointerMove: e => {
        if (dragging) updatePos(e.clientX);
      },
      onPointerUp: e => {
        setDragging(false);
        try {
          e.currentTarget.releasePointerCapture(e.pointerId);
        } catch (_) {}
      },
      style: {
        width: "100%",
        height: 38,
        borderRadius: 19,
        background: "rgba(255, 255, 255, 0.08)",
        border: "1px solid rgba(255, 255, 255, 0.16)",
        position: "relative",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        padding: "0 4px"
      }
    }, React.createElement(GlassDiv, {
      x: posX,
      style: {
        width: 28,
        height: 28,
        borderRadius: 14,
        background: "rgba(255, 255, 255, 0.88)",
        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.4), inset 0 1px 0 #fff",
        position: "absolute",
        top: 4,
        left: 0
      }
    }));
  };
  window.LiquidGlassEngine = {
    Glass,
    GlassDOM,
    GlassMaterial,
    GlassSurface,
    GlassDiv,
    GlassSwitch,
    GlassSlider,
    glassValue,
    deriveGlass,
    animateGlassValue,
    glassEase,
    cubicBezier,
    useLensWobble,
    rubberBand,
    MATERIAL_OPTICS,
    DEFAULT_LENS_PARAMS,
    GlassWebGLRenderer,
    createLensMapGenerator,
    roundedRectMaskUri,
    lensShapeMaskUri
  };
})();