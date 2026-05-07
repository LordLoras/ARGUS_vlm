import type { CSSProperties } from "react";

import { filePathToDataUrl } from "../../lib/format";
import { PlayIcon } from "../../lib/icons";

export function FrameThumbnail({
  src,
  path,
  ar,
  seedA,
  seedB,
  showPlay = true,
  className
}: {
  src?: string | null;
  path?: string | null;
  ar?: string | null;
  seedA?: string;
  seedB?: string;
  showPlay?: boolean;
  className?: string;
}) {
  const resolvedSrc = src ?? (path ? filePathToDataUrl(path) : "");
  const style = {
    "--seed-a": seedA,
    "--seed-b": seedB
  } as CSSProperties;
  return (
    <div className={`thumb ${className ?? ""}`.trim()} style={style}>
      {resolvedSrc ? <img className="thumb-img" src={resolvedSrc} alt="" loading="lazy" /> : null}
      {showPlay && !resolvedSrc ? (
        <span className="play-glyph">
          <PlayIcon size={20} />
        </span>
      ) : null}
      {ar ? <span className="ar">{ar}</span> : null}
    </div>
  );
}
