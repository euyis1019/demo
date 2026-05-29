/** Demo 专用端口 — 与 scripts/demo_ports.sh 保持一致。 */

/** Flask API（避开 macOS AirPlay 占用的 5000）。 */
export const HBM_DEMO_FLASK_PORT = 5050;

/** Vite dev server。 */
export const HBM_DEMO_VITE_PORT = 5173;

export const HBM_DEMO_FLASK_ORIGIN = `http://127.0.0.1:${HBM_DEMO_FLASK_PORT}`;
