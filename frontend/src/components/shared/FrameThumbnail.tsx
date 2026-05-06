import { ImageIcon } from "lucide-react";

import { filePathToDataUrl } from "../../lib/format";

export function FrameThumbnail({ path, alt = "frame" }: { path?: string | null; alt?: string }) {
  const src = filePathToDataUrl(path);
  if (!src) {
    return (
      <div className="flex h-12 w-20 items-center justify-center rounded bg-muted text-muted-foreground">
        <ImageIcon className="h-4 w-4" />
      </div>
    );
  }
  return <img src={src} alt={alt} loading="lazy" className="h-12 w-20 rounded object-cover" />;
}
