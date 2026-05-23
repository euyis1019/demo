/**
 * F0 shell — three-column layout placeholder (F2 will add components).
 * Left: Stats | Center: Main chat | Right: Observer (RDC/GRP).
 */

import "./styles/global.css";

function App() {
  return (
    <div className="app-shell" data-phase="F0">
      <aside className="panel panel--status" aria-label="状态面板">
        <div className="panel__header">Status</div>
        <div className="panel__body">
          <p className="panel__placeholder">Stats · Phase · Turn（F2）</p>
        </div>
      </aside>

      <main className="panel panel--main" aria-label="主交互区">
        <div className="panel__header">Main Chat</div>
        <div className="panel__body">
          <h1 className="app-title">HBM 显存价格保卫战</h1>
          <p className="app-subtitle">前端工程已就绪（Phase F0）</p>
        </div>
      </main>

      <aside className="panel panel--observer" aria-label="上帝视角">
        <div className="panel__header">Observer</div>
        <div className="panel__body">
          <p className="panel__placeholder">RDC · GRP（F2）</p>
        </div>
      </aside>
    </div>
  );
}

export default App;
