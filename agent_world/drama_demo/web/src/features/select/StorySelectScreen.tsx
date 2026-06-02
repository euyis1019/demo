/**
 * 开局选择界面：一行故事卡片（各带封面贴图），最右一张「＋」卡用于新建故事。
 * 点封面卡 = 激活该故事进入开局；点「＋」卡 = 弹出创建故事的窗口（填剧情 → 后台设计+出图 → 自动激活）。
 */

import { useEffect, useState } from "react";
import {
  activateStory,
  createStory,
  deleteStory,
  getJob,
  listStories,
  setSimId,
  type StoryInfo,
} from "../../api/drama";
import { API_ROOT } from "../../api/config";

interface Props {
  /** 故事世界已就绪、可以开玩时回调（带上 story_id 作为当前 sim_id）。 */
  onReady: (simId: string) => void;
}

type Phase = "list" | "creating" | "activating";

/** 某故事的封面贴图 url（assets/cover.png，设计期出图时生成）。 */
function coverUrl(storyId: string): string {
  return `${API_ROOT}/api/drama/stories/${encodeURIComponent(storyId)}/assets/cover.png`;
}

/** 封面图：缺图/加载失败时回退到渐变占位（不显示破图）。 */
function StoryCover({ storyId, hasAssets }: { storyId: string; hasAssets: boolean }) {
  const [failed, setFailed] = useState(!hasAssets);
  if (failed) {
    return <div className="story-card__art story-card__art--fallback" aria-hidden="true" />;
  }
  return (
    <img
      className="story-card__art"
      src={coverUrl(storyId)}
      alt=""
      loading="lazy"
      draggable={false}
      onError={() => setFailed(true)}
    />
  );
}

export function StorySelectScreen({ onReady }: Props) {
  const [stories, setStories] = useState<StoryInfo[]>([]);
  const [phase, setPhase] = useState<Phase>("list");
  const [createOpen, setCreateOpen] = useState(false);
  const [premise, setPremise] = useState("");
  const [title, setTitle] = useState("");
  const [playerId, setPlayerId] = useState("");
  const [status, setStatus] = useState("");
  const [steps, setSteps] = useState<string[]>([]); // 生成进度「日志」：每个新阶段追加一条
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  async function remove(s: StoryInfo) {
    if (deletingId) return;
    const name = s.title || s.story_id;
    if (
      !window.confirm(
        `彻底删除《${name}》？\n这会连同它的后台世界与存档一起删掉，无法恢复。`,
      )
    ) {
      return;
    }
    setDeletingId(s.story_id);
    setError("");
    try {
      await deleteStory(s.story_id);
      setStories((prev) => prev.filter((x) => x.story_id !== s.story_id));
    } catch (e) {
      setError(`删除失败：${String(e)}`);
    } finally {
      setDeletingId(null);
    }
  }

  async function create() {
    const p = premise.trim();
    if (p.length < 8) {
      setError("请输入一段大概的剧情（至少 8 个字）");
      return;
    }
    setCreateOpen(false);
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
      // 不限时生成：素材多的故事生成会久一点，一直轮询到后台返回 done/error 为止。
      for (;;) {
        await new Promise((res) => setTimeout(res, 1500));
        const j = await getJob(jobId);
        const d = j.data;
        if (!d) continue;
        setStatus(d.step);
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
      <div className="select-screen select-screen--busy">
        <div className="select-busy">
          <div className="select-busy__spinner" />
          <div className="select-busy__title">
            {phase === "creating" ? "正在为你准备这个故事…" : "正在启动世界…"}
          </div>
          <div className="select-busy__status">{status || "请稍候…"}</div>
          {phase === "creating" && steps.length > 0 && (
            <div className="select-busy__log">
              {steps.map((s, i) => {
                const isLast = i === steps.length - 1;
                return (
                  <div
                    key={i}
                    className={`select-busy__step${isLast ? " select-busy__step--active" : ""}`}
                  >
                    <span>{isLast ? "▸" : "✓"}</span>
                    <span>{s}</span>
                  </div>
                );
              })}
            </div>
          )}
          <div className="select-busy__foot">设计剧情 + 出图约需 1–3 分钟，请勿关闭页面。</div>
        </div>
      </div>
    );
  }

  return (
    <div className="select-screen">
      <header className="select-screen__head">
        <h1 className="select-screen__title">选 择 一 个 故 事</h1>
        <p className="select-screen__sub">
          挑一张剧本，或写一段你自己的剧情，让 AI 为你搭建一座今夜的舞台。
        </p>
      </header>

      {error && <div className="select-screen__error">{error}</div>}

      <div className="select-row" role="list">
        {stories.map((s) => (
          <div key={s.story_id} className="story-card-wrap" role="listitem">
            <button
              type="button"
              className="story-card"
              onClick={() => void activate(s.story_id)}
              disabled={deletingId === s.story_id}
              title={s.title || s.story_id}
            >
              <StoryCover storyId={s.story_id} hasAssets={s.has_assets} />
              <div className="story-card__veil" />
              <div className="story-card__body">
                <div className="story-card__title">{s.title || s.story_id}</div>
                <div className="story-card__meta">
                  {s.agents} 个角色 · {s.has_assets ? "含立绘" : "暂无图"}
                </div>
              </div>
              <span className="story-card__enter">进入 →</span>
            </button>
            <button
              type="button"
              className="story-card__delete"
              onClick={() => void remove(s)}
              disabled={deletingId === s.story_id}
              aria-label={`删除故事 ${s.title || s.story_id}`}
              title="彻底删除这个故事（含后台世界）"
            >
              {deletingId === s.story_id ? "⏳" : "✕"}
            </button>
          </div>
        ))}

        <button
          type="button"
          className="story-card story-card--add"
          onClick={() => setCreateOpen(true)}
          title="新建故事"
        >
          <div className="story-card__plus" aria-hidden="true">
            ＋
          </div>
          <div className="story-card__add-label">新建故事</div>
          <div className="story-card__add-hint">写一段剧情，AI 来搭世界</div>
        </button>
      </div>

      {createOpen && (
        <div
          className="select-modal"
          role="dialog"
          aria-modal="true"
          aria-label="新建故事"
          onClick={() => setCreateOpen(false)}
        >
          <div className="select-modal__panel" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="select-modal__close"
              onClick={() => setCreateOpen(false)}
              aria-label="关闭"
            >
              ✕
            </button>
            <h2 className="select-modal__title">✦ 新建故事</h2>
            <p className="select-modal__hint">
              写一段大概的剧情，AI 会搭好世界、出好立绘。别把「标题：」之类字样写进剧情里。
            </p>

            <label className="select-modal__field">
              <span className="select-modal__label">标题（可留空，AI 会自动取）</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="如：静屿灯塔谋杀案"
                className="select-modal__input"
              />
            </label>

            <label className="select-modal__field">
              <span className="select-modal__label">剧情</span>
              <textarea
                value={premise}
                onChange={(e) => setPremise(e.target.value)}
                placeholder="写一段大概的剧情，纯文字即可：如 暴雨夜孤岛灯塔庄园，主人离奇身亡，五个困在岛上的人各怀心事，你是受托上岛的侦探，要在三天内查清真相…"
                rows={5}
                className="select-modal__input select-modal__textarea"
              />
            </label>

            <label className="select-modal__field">
              <span className="select-modal__label">你的身份（可留空）</span>
              <input
                value={playerId}
                onChange={(e) => setPlayerId(e.target.value)}
                placeholder="如：受托上岛查案的私家侦探"
                className="select-modal__input"
              />
            </label>

            {error && <div className="select-modal__error">{error}</div>}

            <div className="select-modal__actions">
              <button
                type="button"
                className="select-modal__btn select-modal__btn--ghost"
                onClick={() => setCreateOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="select-modal__btn select-modal__btn--go"
                onClick={() => void create()}
              >
                开始准备这个故事
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
