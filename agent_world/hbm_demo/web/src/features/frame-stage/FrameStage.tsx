/**
 * F18 — 实时整帧画面舞台。
 * 显示后端每 tick 文生图生成的整帧游戏画面（base64 data-uri）。
 * 出图异步滞后于世界 tick，故无帧时显示占位提示，有帧后只在 tick 变化时换图。
 */

interface FrameStageProps {
  frame: { tick: number; dataUri: string } | null;
  placeLabel?: string;
  worldTick?: number;
}

export function FrameStage({ frame, placeLabel, worldTick }: FrameStageProps) {
  return (
    <div className="frame-stage">
      <div className="frame-stage__canvas">
        {frame ? (
          <img
            className="frame-stage__img"
            src={frame.dataUri}
            alt={`AI 生成画面 · tick ${frame.tick}`}
          />
        ) : (
          <div className="frame-stage__placeholder">
            <div className="frame-stage__spinner" />
            <span>AI 正在生成游戏画面…</span>
          </div>
        )}
      </div>
      <div className="frame-stage__meta">
        {placeLabel ? <span>{placeLabel}</span> : null}
        <span className="frame-stage__ticks">
          画面 tick {frame?.tick ?? "—"}
          {worldTick !== undefined ? ` / 世界 tick ${worldTick}` : ""}
        </span>
      </div>
    </div>
  );
}
