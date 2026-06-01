/**
 * 开局选择界面：选一个已有故事，或输入一段剧情新建。
 * 新建 = 后台 Designer→Casting→Writer 设计 + 出图，准备好后激活世界 → 回到正常开局流程。
 */

import { useEffect, useState } from "react";
import {
  activateStory,
  createStory,
  getJob,
  listStories,
  setSimId,
  type StoryInfo,
} from "../../api/drama";

interface Props {
  /** 故事世界已就绪、可以开玩时回调（带上 story_id 作为当前 sim_id）。 */
  onReady: (simId: string) => void;
}

type Phase = "list" | "creating" | "activating";

const wrap: React.CSSProperties = {
  minHeight: "100vh",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: 24,
  background: "radial-gradient(1200px 600px at 50% -10%, #1b2440 0%, #0a0e1a 60%)",
  color: "#e8ecf5",
  fontFamily: "'Noto Sans SC', system-ui, sans-serif",
  padding: 32,
};

const fieldStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: 12,
  borderRadius: 10,
  border: "1px solid #2a3656",
  background: "#0c1322",
  color: "#e8ecf5",
  fontFamily: "inherit",
  fontSize: 14,
};

export function StorySelectScreen({ onReady }: Props) {
  const [stories, setStories] = useState<StoryInfo[]>([]);
  const [phase, setPhase] = useState<Phase>("list");
  const [premise, setPremise] = useState("");
  const [title, setTitle] = useState("");
  const [playerId, setPlayerId] = useState("");
  const [status, setStatus] = useState("");
  const [steps, setSteps] = useState<string[]>([]); // 生成进度「日志」：每个新阶段追加一条，给玩家看到进展
  const [error, setError] = useState("");

  useEffect(() => {
    listStories()
      .then((r) => setStories(r.data?.stories ?? []))
      .catch((e) => setError(`加载故事失败：${String(e)}`));
  }, []);

  async function activate(simId: string) {
    setPhase("activating");
    setStatus("正在启动后台世界…（播种世界、唤醒 NPC）");
    setError("");
    try {
      const r = await activateStory(simId);
      if (r.data?.ready) {
        setSimId(simId);
        onReady(simId);
      } else {
        setError("世界未能就绪，请重试");
        setPhase("list");
      }
    } catch (e) {
      setError(`启动世界失败：${String(e)}`);
      setPhase("list");
    }
  }

  async function create() {
    const p = premise.trim();
    if (p.length < 8) {
      setError("请输入一段大概的剧情（至少 8 个字）");
      return;
    }
    setPhase("creating");
    setError("");
    setStatus("提交剧情中…");
    setSteps([]);
    try {
      const r = await createStory({
        premise: p,
        title: title.trim() || undefined,
        player: playerId.trim() || undefined,
      });
      const jobId = r.data?.job_id;
      if (!jobId) {
        setError("创建失败");
        setPhase("list");
        return;
      }
      // 不限时生成：素材多的故事生成会久一点，一直轮询到后台返回 done/error 为止（不再 10 分钟超时取消）。
      for (;;) {
        await new Promise((res) => setTimeout(res, 1500));
        const j = await getJob(jobId);
        const d = j.data;
        if (!d) continue;
        setStatus(d.step);
        // 阶段变化就往「进度日志」追一条（同一句不重复），让玩家看到一步步推进
        setSteps((prev) => (prev[prev.length - 1] === d.step ? prev : [...prev, d.step]));
        if (d.status === "done" && d.story_id) {
          await activate(d.story_id);
          return;
        }
        if (d.status === "error") {
          setError(d.error ?? "生成失败");
          setPhase("list");
          return;
        }
      }
    } catch (e) {
      setError(`新建失败：${String(e)}`);
      setPhase("list");
    }
  }

  if (phase === "creating" || phase === "activating") {
    return (
      <div style={wrap}>
        <div style={{ fontSize: 22, fontWeight: 600 }}>
          {phase === "creating" ? "正在为你准备这个故事…" : "正在启动世界…"}
        </div>
        <div style={{ width: 64, height: 64, border: "4px solid #2a3656", borderTopColor: "#6ea8ff", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        <div style={{ color: "#cfe0ff", fontSize: 16, fontWeight: 600, maxWidth: 560, textAlign: "center", minHeight: 22 }}>
          {status || "请稍候…"}
        </div>
        {phase === "creating" && steps.length > 0 && (
          <div
            style={{
              width: "min(560px, 92vw)",
              maxHeight: 200,
              overflowY: "auto",
              background: "#0c1322",
              border: "1px solid #1e2740",
              borderRadius: 10,
              padding: "10px 14px",
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            {steps.map((s, i) => {
              const isLast = i === steps.length - 1;
              return (
                <div key={i} style={{ color: isLast ? "#9fdcff" : "#6b7aa0", fontSize: 13, display: "flex", gap: 8 }}>
                  <span>{isLast ? "▸" : "✓"}</span>
                  <span>{s}</span>
                </div>
              );
            })}
          </div>
        )}
        <div style={{ color: "#5f6f8f", fontSize: 13 }}>
          设计剧情 + 出图约需 1–3 分钟，请勿关闭页面。
        </div>
        <style>{"@keyframes spin{to{transform:rotate(360deg)}}"}</style>
      </div>
    );
  }

  return (
    <div style={wrap}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: 2 }}>选择一个故事</div>
        <div style={{ color: "#9fb0d0", marginTop: 8 }}>挑一个已有的剧本，或写一段你自己的剧情让 AI 来搭建世界。</div>
      </div>

      {error && (
        <div style={{ color: "#ff8a8a", background: "#2a1620", padding: "8px 16px", borderRadius: 8 }}>{error}</div>
      )}

      <div style={{ display: "grid", gap: 12, width: "min(680px, 92vw)" }}>
        {stories.length === 0 && <div style={{ color: "#7f8fb0" }}>暂无已有故事，新建一个吧。</div>}
        {stories.map((s) => (
          <button
            key={s.story_id}
            onClick={() => void activate(s.story_id)}
            style={{
              textAlign: "left",
              padding: "16px 18px",
              borderRadius: 12,
              border: "1px solid #2a3656",
              background: "linear-gradient(180deg,#141b30,#0e1424)",
              color: "#e8ecf5",
              cursor: "pointer",
            }}
          >
            <div style={{ fontSize: 17, fontWeight: 600 }}>{s.title || s.story_id}</div>
            <div style={{ color: "#7f8fb0", fontSize: 13, marginTop: 4 }}>
              {s.agents} 个角色 · {s.has_assets ? "已有图片素材" : "暂无图片"} · 点击进入
            </div>
          </button>
        ))}
      </div>

      <div style={{ width: "min(680px, 92vw)", borderTop: "1px solid #1e2740", paddingTop: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>✦ 新建故事（分三栏填，别把「标题：」之类字样写进剧情里）</div>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="标题（可留空，AI 会自动取）：如 静屿灯塔谋杀案"
          style={fieldStyle}
        />
        <textarea
          value={premise}
          onChange={(e) => setPremise(e.target.value)}
          placeholder="剧情（写一段大概的剧情，纯文字即可）：如 暴雨夜孤岛灯塔庄园，主人离奇身亡，五个困在岛上的人各怀心事，你是受托上岛的侦探，要在三天内查清真相…"
          rows={4}
          style={{ ...fieldStyle, resize: "vertical", marginTop: 8 }}
        />
        <input
          value={playerId}
          onChange={(e) => setPlayerId(e.target.value)}
          placeholder="你的身份（可留空）：如 受托上岛查案的私家侦探"
          style={{ ...fieldStyle, marginTop: 8 }}
        />
        <button
          onClick={() => void create()}
          style={{
            marginTop: 10,
            padding: "12px 22px",
            borderRadius: 10,
            border: "none",
            background: "linear-gradient(90deg,#5b8cff,#7a6bff)",
            color: "#fff",
            fontSize: 15,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          开始准备这个故事
        </button>
      </div>
    </div>
  );
}
