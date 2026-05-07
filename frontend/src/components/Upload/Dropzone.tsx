import { useRef, useState } from "react";

import { UploadIcon } from "../../lib/icons";

export function Dropzone({ onFile }: { onFile: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <div className="upload-card">
      <div className="upload-card-head">
        <span className="step-num">1</span>
        <span>Choose video</span>
      </div>
      <div
        className={`dropzone ${drag ? "drag" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const file = e.dataTransfer.files?.[0];
          if (file) onFile(file);
        }}
      >
        <div className="glyph">
          <UploadIcon size={20} />
        </div>
        <h3>Drop a video here</h3>
        <p>or click to browse</p>
        <div className="hint">MP4 · MOV · WebM · up to 200 MB</div>
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
    </div>
  );
}
