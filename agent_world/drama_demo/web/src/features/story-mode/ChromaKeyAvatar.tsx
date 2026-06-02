import { useEffect, useState } from "react";
import { getResolvedAvatar, resolveAvatar } from "./greenScreenKey";

export interface ChromaKeyAvatarProps {
  src: string;
  className?: string;
  /** 情绪变体图缺失（404/处理失败）时回退到此基础立绘。 */
  fallbackSrc?: string;
}

/** Avatar display — uses pre-keyed PNG when available, else runtime green removal.
 *  关键：换情绪(src 变)时，若该图已被解析/预热进缓存，则**同步本帧切换**——立绘与字幕同步，不再慢半拍。
 *  src 加载/处理失败时（如缺该情绪的立绘变体）回退到 fallbackSrc。 */
export function ChromaKeyAvatar({ src, className, fallbackSrc }: ChromaKeyAvatarProps) {
  // 初值同步取缓存：换到一个「之前出现过/已预热」的情绪时，首帧就是对的图，不闪旧表情。
  const [displaySrc, setDisplaySrc] = useState<string | null>(
    () => getResolvedAvatar(src) ?? null,
  );

  useEffect(() => {
    // 命中缓存：本帧即切（和字幕同步），不走异步。
    const cached = getResolvedAvatar(src);
    if (cached) {
      setDisplaySrc(cached);
      return;
    }
    let cancelled = false;
    void resolveAvatar(src)
      .then((out) => {
        if (!cancelled) {
          setDisplaySrc(out);
        }
      })
      .catch(async () => {
        if (cancelled) {
          return;
        }
        // src 失败（情绪变体缺图等）→ 回退基础立绘再解析一次
        if (fallbackSrc && fallbackSrc !== src) {
          if (import.meta.env.DEV) {
            console.warn(`[立绘] 情绪变体图缺失，回退基础图：${src}（体检 P6）`);
          }
          try {
            const out = await resolveAvatar(fallbackSrc);
            if (!cancelled) {
              setDisplaySrc(out);
            }
            return;
          } catch {
            /* fall through */
          }
        }
        if (!cancelled) {
          setDisplaySrc(fallbackSrc ?? src);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [src, fallbackSrc]);

  if (!displaySrc) {
    return <div className={className} aria-hidden="true" />;
  }

  return (
    <img
      className={className}
      src={displaySrc}
      alt=""
      draggable={false}
      // 最终图仍 404（如玩家无立绘 player.png、或某角色出图失败）→ 优雅隐藏，不显示破图占位符
      onError={() => setDisplaySrc(null)}
    />
  );
}
