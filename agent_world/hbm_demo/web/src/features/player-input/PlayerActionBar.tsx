import { useState } from "react";
import { postPlayerAction, type PlayerActionRequest } from "../../api/hbm";
import { PLAYER_AGENT_ID, VIRTUAL_PLAYER_AGENT_ID } from "../../constants/agents";
import { ROOM_GRID } from "../../utils/places";

export interface PlayerActionBarProps {
  /** 当前地点（移动默认排除）。 */
  placeId: string;
  /** agent id → 名称（用于私信目标下拉）。 */
  nameMap: Record<string, string>;
  disabled?: boolean;
}

/**
 * 玩家主动动作条：移动 / 私信 / 加群。在 F2F 台词之外给玩家更多动作（需求二）。
 * 加群受后端门控（须先 F2F 见过群里某成员并得其同意），失败时显示原因。
 */
export function PlayerActionBar({ placeId, nameMap, disabled }: PlayerActionBarProps) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const agentOptions = Object.keys(nameMap)
    .filter((id) => id !== PLAYER_AGENT_ID && id !== VIRTUAL_PLAYER_AGENT_ID)
    .sort((a, b) => Number(a) - Number(b));

  const [movePlace, setMovePlace] = useState<string>("");
  const [rdcTarget, setRdcTarget] = useState<string>(agentOptions[0] ?? "");
  const [rdcText, setRdcText] = useState<string>("");
  const [groupId, setGroupId] = useState<string>("");

  async function run(request: PlayerActionRequest, label: string) {
    if (busy || disabled) return;
    setBusy(true);
    setStatus(null);
    try {
      const res = await postPlayerAction(request);
      if (res.success && res.data?.accepted) {
        setStatus(`✓ ${label}已发出`);
      } else {
        const reason = res.data?.hint ?? res.data?.reason ?? res.error ?? "被拒绝";
        setStatus(`✗ ${label}失败：${reason}`);
      }
    } catch {
      setStatus(`✗ ${label}请求出错`);
    } finally {
      setBusy(false);
    }
  }

  const off = disabled || busy;

  return (
    <div className="player-action-bar">
      <div className="player-action-bar__row">
        <label>移动</label>
        <select value={movePlace} onChange={(e) => setMovePlace(e.target.value)} disabled={off}>
          <option value="">选择地点…</option>
          {ROOM_GRID.filter((p) => p !== placeId).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={off || !movePlace}
          onClick={() => void run({ action: "move", place_id: movePlace }, "移动")}
        >
          去
        </button>
      </div>

      <div className="player-action-bar__row">
        <label>私信</label>
        <select value={rdcTarget} onChange={(e) => setRdcTarget(e.target.value)} disabled={off}>
          {agentOptions.map((id) => (
            <option key={id} value={id}>
              {nameMap[id] ?? id}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={rdcText}
          placeholder="私信内容…"
          onChange={(e) => setRdcText(e.target.value)}
          disabled={off}
        />
        <button
          type="button"
          disabled={off || !rdcTarget || !rdcText.trim()}
          onClick={() =>
            void run(
              { action: "rdc", target_id: Number(rdcTarget), content: rdcText.trim() },
              "私信",
            ).then(() => setRdcText(""))
          }
        >
          发
        </button>
      </div>

      <div className="player-action-bar__row">
        <label>加群</label>
        <input
          type="text"
          inputMode="numeric"
          value={groupId}
          placeholder="群号"
          onChange={(e) => setGroupId(e.target.value.replace(/\D/g, ""))}
          disabled={off}
        />
        <button
          type="button"
          disabled={off || !groupId}
          onClick={() => void run({ action: "grp", group_id: Number(groupId) }, "加群")}
        >
          加入
        </button>
      </div>

      {status ? <p className="player-action-bar__status">{status}</p> : null}
    </div>
  );
}
