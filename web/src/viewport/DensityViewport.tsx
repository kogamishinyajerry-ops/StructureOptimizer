import { useCallback, useEffect, useRef } from "react";
import { decodeDensity } from "../api/types";
import "./DensityViewport.css";

interface Props {
  density: string | null; // base64 uint8
  shape: [number, number] | null; // [nely, nelx]
  running: boolean;
}

// Engine-native colormap: void -> material, linear in density.
const VOID = [245, 249, 251];
const MATERIAL = [12, 62, 78];

/**
 * The showcase. Renders the [0,1] density field to a crisp, aspect-correct
 * canvas, redrawing each frame as the topology converges. We draw at element
 * resolution into a small offscreen buffer, then upscale with nearest-neighbor
 * so individual elements stay sharp (CAE convention) while filling the well.
 */
export function DensityViewport({ density, shape, running }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const offscreenRef = useRef<HTMLCanvasElement | null>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !density || !shape) return;
    const [nely, nelx] = shape;
    const field = decodeDensity(density);
    if (field.length !== nely * nelx) return;

    // Offscreen at element resolution.
    let off = offscreenRef.current;
    if (!off || off.width !== nelx || off.height !== nely) {
      off = document.createElement("canvas");
      off.width = nelx;
      off.height = nely;
      offscreenRef.current = off;
    }
    const octx = off.getContext("2d")!;
    const img = octx.createImageData(nelx, nely);
    for (let i = 0; i < field.length; i++) {
      const d = field[i];
      const j = i * 4;
      img.data[j] = VOID[0] + (MATERIAL[0] - VOID[0]) * d;
      img.data[j + 1] = VOID[1] + (MATERIAL[1] - VOID[1]) * d;
      img.data[j + 2] = VOID[2] + (MATERIAL[2] - VOID[2]) * d;
      img.data[j + 3] = 255;
    }
    octx.putImageData(img, 0, 0);

    // Fit into the canvas backing store (CSS box * DPR), centered.
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight;
    if (canvas.width !== cssW * dpr || canvas.height !== cssH * dpr) {
      canvas.width = cssW * dpr;
      canvas.height = cssH * dpr;
    }
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const scale = Math.min((cssW * dpr) / nelx, (cssH * dpr) / nely);
    const drawW = nelx * scale;
    const drawH = nely * scale;
    const ox = (canvas.width - drawW) / 2;
    const oy = (canvas.height - drawH) / 2;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, ox, oy, drawW, drawH);
  }, [density, shape]);

  // Repaint on every new frame (density/shape change).
  useEffect(() => {
    draw();
  }, [draw]);

  // Re-fit the backing store + repaint on resize. The draw routine sizes the
  // bitmap from the CSS box, but that box only changes on window/layout resize —
  // not on a React render. Without this, the terminal 'done' state and every
  // reopened/compared static run (no further frames) keep a stale, CSS-stretched
  // image after a resize, breaking the component's crispness contract.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(() => draw());
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [draw]);

  return (
    <div className={`viewport ${running ? "is-running" : ""}`}>
      {density ? (
        <canvas ref={canvasRef} className="viewport-canvas" />
      ) : (
        <div className="viewport-empty">
          <div className="viewport-empty-glyph" aria-hidden />
          <p>Select a benchmark and run an optimization to see the topology emerge.</p>
        </div>
      )}
      {running && <div className="viewport-scanline" aria-hidden />}
    </div>
  );
}
