import { useEffect, useState } from "react";
import { chromaKeyGreenToDataUrl, imageHasTransparency } from "./greenScreenKey";

export interface ChromaKeyAvatarProps {
  src: string;
  className?: string;
}

/** Avatar display — uses pre-keyed PNG when available, else runtime green removal. */
export function ChromaKeyAvatar({ src, className }: ChromaKeyAvatarProps) {
  const [displaySrc, setDisplaySrc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const keyed = await imageHasTransparency(src);
        if (cancelled) {
          return;
        }
        if (keyed) {
          setDisplaySrc(src);
          return;
        }
        const processed = await chromaKeyGreenToDataUrl(src);
        if (!cancelled) {
          setDisplaySrc(processed);
        }
      } catch {
        if (!cancelled) {
          setDisplaySrc(src);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [src]);

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
