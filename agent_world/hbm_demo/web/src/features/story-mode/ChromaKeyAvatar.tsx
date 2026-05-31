import { useEffect, useState } from "react";
import { chromaKeyGreenToDataUrl, imageHasTransparency } from "./greenScreenKey";

export interface ChromaKeyAvatarProps {
  src: string;
  className?: string;
  /** 情绪变体图缺失（404/处理失败）时回退到此基础立绘。 */
  fallbackSrc?: string;
}

/** Avatar display — uses pre-keyed PNG when available, else runtime green removal.
 *  src 加载/处理失败时（如缺该情绪的立绘变体）回退到 fallbackSrc。 */
export function ChromaKeyAvatar({ src, className, fallbackSrc }: ChromaKeyAvatarProps) {
  const [displaySrc, setDisplaySrc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function process(url: string): Promise<string> {
      const keyed = await imageHasTransparency(url);
      return keyed ? url : chromaKeyGreenToDataUrl(url);
    }

    void (async () => {
      try {
        const out = await process(src);
        if (!cancelled) {
          setDisplaySrc(out);
        }
      } catch {
        if (cancelled) {
          return;
        }
        // src 失败（情绪变体缺图等）→ 回退基础立绘再处理一次
        if (fallbackSrc && fallbackSrc !== src) {
          if (import.meta.env.DEV) {
            console.warn(`[立绘] 情绪变体图缺失，回退基础图：${src}（体检 P6）`);
          }
          try {
            const out = await process(fallbackSrc);
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
      }
    })();

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
    />
  );
}
