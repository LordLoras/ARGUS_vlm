import { useRef, useState } from "react";

import { UploadIcon } from "../../lib/icons";

export function Dropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const choose = (files: FileList | null | undefined) => {
    const selected = Array.from(files ?? []);
    if (selected.length) onFiles(selected);
  };

  return (
    <>
      <input
        ref={input}
        type="file"
        multiple
        accept="video/mp4,video/quicktime,video/webm"
        aria-label="Choose video ad files"
        style={{ display: "none" }}
        onChange={(e) => {
          choose(e.target.files);
          e.currentTarget.value = "";
        }}
      />
      <button
        type="button"
        className={`dropzone ${drag ? "drag" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          choose(e.dataTransfer.files);
        }}
      >
        <span className="dropzone-glow" />
        <span className="dropzone-glyph">
          <UploadIcon size={24} />
        </span>
        <span className="dropzone-title">Drop videos here</span>
        <span className="dropzone-p">or click to browse. Multiple clips are queued as separate jobs.</span>
        <span className="dropzone-hints">
          <span>MP4</span>
          <span>MOV</span>
          <span>WebM</span>
          <span>up to 200 MB</span>
        </span>
      </button>
    </>
  );
}
