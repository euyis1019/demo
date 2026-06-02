import { useState } from "react";
import { postPlayerAction } from "../../api/drama";
import { placeDisplayName } from "../../utils/places";

export interface StoryPlaceListProps {
  /** 当前所在地点。 */
  placeId: string;
  /** 世界全部地点。 */
  places: string[];
  disabled?: boolean;
  /** 后端受理移动后回调，供上层乐观把界面立刻切到新地点（不必等 world-delta 轮询）。 */
  onMoved?: (placeId: string) => void;
}

/**
 * 左侧地点列表（#4）：列出世界全部地点，点击即移动过去——玩家自由走动的主入口。
 * 移动经 /player-action move；后端已改为「玩家位置由玩家自己主导、不再被剧情拽走」，故点哪去哪、稳定停留。
 */
export function StoryPlaceList({ placeId, places, disabled, onMoved }: StoryPlaceListProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function go(target: string) {
    if (busy || disabled || target === placeId) return;
    setBusy(target);
    setErr(null);
    try {
      const res = await postPlayerAction({ action: "move", place_id: target });
      if (res.success && res.data?.accepted) {
        onMoved?.(target); // 受理成功 → 立刻切到新地点（乐观），不等轮询
      } else {
        setErr(res.data?.reason ?? res.error ?? "去不了");
      }
    } catch {
      setErr("移动出错");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="story-place-list">
      <div className="story-place-list__title">📍 去哪儿</div>
      {places.map((p) => {
        const current = p === placeId;
        return (
          <button
            key={p}
            type="button"
            className={`story-place-list__item ${current ? "is-current" : ""}`}
            disabled={disabled || busy !== null || current}
            onClick={() => void go(p)}
            title={current ? "你在这里" : `移动到 ${placeDisplayName(p)}`}
          >
            <span className="story-place-list__dot">{current ? "◉" : "○"}</span>
            <span className="story-place-list__name">{placeDisplayName(p)}</span>
            {busy === p ? <span className="story-place-list__spin">…</span> : null}
          </button>
        );
      })}
      {err ? <div className="story-place-list__err">{err}</div> : null}
    </div>
  );
}
