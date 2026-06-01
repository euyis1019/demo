const DATA_URL_CACHE = new Map<string, string>();

interface Rgb {
  r: number;
  g: number;
  b: number;
}

function hueDeg(r: number, g: number, b: number): number {
  const rf = r / 255;
  const gf = g / 255;
  const bf = b / 255;
  const mx = Math.max(rf, gf, bf);
  const mn = Math.min(rf, gf, bf);
  const d = mx - mn;
  if (d < 0.025) {
    return 0;
  }
  let h: number;
  if (mx === gf) {
    h = 60 * ((bf - rf) / d + 2);
  } else if (mx === rf) {
    h = 60 * (((gf - bf) / d) % 6);
  } else {
    h = 60 * ((rf - gf) / d + 4);
  }
  return ((h % 360) + 360) % 360;
}

function greenScreenAlpha(r: number, g: number, b: number): number {
  const rf = r / 255;
  const gf = g / 255;
  const bf = b / 255;
  const mx = Math.max(rf, gf, bf);
  const mn = Math.min(rf, gf, bf);
  const delta = mx - mn;
  if (delta < 0.025) {
    return 255;
  }

  const hue = hueDeg(r, g, b);
  const sat = mx > 0 ? delta / mx : 0;
  const greenExcess = gf - Math.max(rf, bf);
  const isGreenHue = hue >= 48 && hue <= 168;

  if (!isGreenHue || gf < 0.22) {
    return 255;
  }

  let score = 0;
  score += Math.min(1, greenExcess / 0.35);
  score += Math.min(0.45, sat * 0.9);
  if (hue >= 70 && hue <= 145) {
    score += 0.25;
  }
  if (gf > rf && gf > bf) {
    score += 0.15;
  }

  if (score >= 0.72) {
    return 0;
  }
  if (score >= 0.42) {
    const t = (score - 0.42) / 0.3;
    return Math.max(0, Math.min(255, Math.round(255 * (1 - t))));
  }
  return 255;
}

function despill(r: number, g: number, b: number, alpha: number): Rgb {
  if (alpha >= 250) {
    return { r, g, b };
  }
  const cap = Math.max(r, b) + 8;
  return { r, g: Math.min(g, cap), b };
}

/** Remove yellow-green / pure green screen pixels; cache by source URL. */
export function chromaKeyGreenToDataUrl(src: string): Promise<string> {
  const cached = DATA_URL_CACHE.get(src);
  if (cached) {
    return Promise.resolve(cached);
  }

  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = "async";
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          resolve(src);
          return;
        }
        ctx.drawImage(img, 0, 0);
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
          const r = pixels[i];
          const g = pixels[i + 1];
          const b = pixels[i + 2];
          const srcAlpha = pixels[i + 3];
          if (srcAlpha === 0) {
            continue;
          }
          const alpha = Math.min(srcAlpha, greenScreenAlpha(r, g, b));
          const spilled = despill(r, g, b, alpha);
          pixels[i] = spilled.r;
          pixels[i + 1] = spilled.g;
          pixels[i + 2] = spilled.b;
          pixels[i + 3] = alpha;
        }

        ctx.putImageData(imageData, 0, 0);
        const dataUrl = canvas.toDataURL("image/png");
        DATA_URL_CACHE.set(src, dataUrl);
        resolve(dataUrl);
      } catch {
        resolve(src);
      }
    };
    img.onerror = () => reject(new Error(`avatar load failed: ${src}`));
    img.src = src;
  });
}

/** True when PNG already has meaningful transparency (pre-processed asset). */
export async function imageHasTransparency(src: string): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const sample = 48;
        const canvas = document.createElement("canvas");
        canvas.width = sample;
        canvas.height = sample;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          resolve(false);
          return;
        }
        ctx.drawImage(img, 0, 0, sample, sample);
        const { data } = ctx.getImageData(0, 0, sample, sample);
        let transparent = 0;
        for (let i = 3; i < data.length; i += 4) {
          if (data[i] < 20) {
            transparent += 1;
          }
        }
        resolve(transparent / (sample * sample) > 0.08);
      } catch {
        resolve(false);
      }
    };
    img.onerror = () => resolve(false);
    img.src = src;
  });
}
