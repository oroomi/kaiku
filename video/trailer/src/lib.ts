export const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const ss = (x: number) => {
  x = clamp(x);
  return x * x * (3 - 2 * x);
};
export const lin = (x: number) => clamp(x);
export const eo3 = (x: number) => 1 - Math.pow(1 - clamp(x), 3);
export const eo2 = (x: number) => 1 - Math.pow(1 - clamp(x), 2);
export const ei3 = (x: number) => Math.pow(clamp(x), 3);
/** ease-out with overshoot (back) */
export const eob = (x: number, k = 1.9) => {
  x = clamp(x) - 1;
  return 1 + (k + 1) * x * x * x + k * x * x;
};
export const seg = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
export type Ease = (x: number) => number;

/** keyframes: rows [t, v0, v1, ...] -> interpolated values (eased per segment) */
export function KV(t: number, rows: number[][], ease: Ease = ss): number[] {
  if (t <= rows[0][0]) return rows[0].slice(1);
  const last = rows[rows.length - 1];
  if (t >= last[0]) return last.slice(1);
  for (let i = 0; i < rows.length - 1; i++) {
    const a = rows[i];
    const b = rows[i + 1];
    if (t >= a[0] && t <= b[0]) {
      const p = ease((t - a[0]) / (b[0] - a[0]));
      return a.slice(1).map((v, j) => v + (b[j + 1] - v) * p);
    }
  }
  return last.slice(1);
}
export const K = (t: number, rows: number[][], ease: Ease = ss): number => KV(t, rows, ease)[0];

export const hex = (h: string): [number, number, number] => {
  const n = parseInt(h.replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
export const mixc = (a: [number, number, number], b: [number, number, number], p: number): [number, number, number] => [
  a[0] + (b[0] - a[0]) * p,
  a[1] + (b[1] - a[1]) * p,
  a[2] + (b[2] - a[2]) * p,
];
export const rgba = (c: number[], a = 1) => `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${a})`;

/** Catmull-Rom through keyframe rows [t, v...] (smooth velocity through keys) */
export function KC(t: number, rows: number[][]): number[] {
  if (t <= rows[0][0]) return rows[0].slice(1);
  const n = rows.length;
  if (t >= rows[n - 1][0]) return rows[n - 1].slice(1);
  let i = 0;
  while (i < n - 2 && t > rows[i + 1][0]) i++;
  const p0 = rows[Math.max(0, i - 1)];
  const p1 = rows[i];
  const p2 = rows[i + 1];
  const p3 = rows[Math.min(n - 1, i + 2)];
  const u = (t - p1[0]) / (p2[0] - p1[0]);
  const u2 = u * u;
  const u3 = u2 * u;
  return p1.slice(1).map((_, j) => {
    const a = p0[j + 1], b = p1[j + 1], c = p2[j + 1], d = p3[j + 1];
    return 0.5 * (2 * b + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u2 + (-a + 3 * b - 3 * c + d) * u3);
  });
}
