import { useRef, useState } from "react";

import { UploadIcon } from "../../lib/icons";

export function Dropzone({ onFile }: { onFile: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <div
      className={`dropzone ${drag ? "drag" : ""}`}
      onClick={() => input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <div className="dropzone-glow" />
      <div className="dropzone-glyph">
        <UploadIcon size={24} />
      </div>
      <h3>Drop a video here</h3>
      <p className="dropzone-p">or click to browse</p>
      <div className="dropzone-hints">
        <span>MP4</span>
        <span>MOV</span>
        <span>WebM</span>
        <span>up to 200 MB</span>
      </div>
      <input
        ref={input}
        type="file"
        accept="video/mp4,video/quicktime,video/webm"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
    </div>
  );
}
