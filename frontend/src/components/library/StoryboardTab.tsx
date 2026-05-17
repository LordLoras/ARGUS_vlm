import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../../lib/api-client";
import { filePathToDataUrl, formatDuration } from "../../lib/format";
import { FilmIcon, SparkleIcon } from "../../lib/icons";
import type { Storyboard } from "../../lib/types";
import { TimestampChip } from "../shared/TimestampChip";

export function StoryboardTab({ adId, onSeek }: { adId: string; onSeek?: (timeMs: number) => void }) {
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const mutation = useMutation({
    mutationFn: () => api.createStoryboard(adId),
    onSuccess: setStoryboard
  });

  useEffect(() => {
    setStoryboard(null);
    mutation.reset();
  }, [adId]);

  return (
    <div className="dcard">
      <div className="dcard-head">
        <span>Production storyboard</span>
        {storyboard ? <span className="count-pill">{storyboard.shot_count}</span> : null}
      </div>
      <div className="dcard-body">
        <div className="storyboard-toolbar">
          <button
            className="btn btn-primary"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            <SparkleIcon size={12} />
            <span>{mutation.isPending ? "Building" : storyboard ? "Rebuild" : "Build storyboard"}</span>
          </button>
          {storyboard ? (
            <span className="mono storyboard-meta">{storyboard.method}</span>
          ) : (
            <span className="mono storyboard-meta">pHash shots, OCR text, transcript overlap</span>
          )}
        </div>

        {mutation.isError ? (
          <div className="obs-empty">Storyboard generation failed.</div>
        ) : null}

        {!storyboard && !mutation.isPending ? (
          <div className="empty-block storyboard-empty">
            <div className="icon-wrap">
              <FilmIcon size={18} />
            </div>
            <div>Generate a shot-by-shot readout from stored frames, OCR, and transcript.</div>
          </div>
        ) : null}

        {storyboard ? (
          <div className="storyboard-list">
            {storyboard.shots.map((shot) => {
              const src = filePathToDataUrl(shot.representative_frame_path);
              return (
                <div className="storyboard-shot" key={shot.shot_index}>
                  <div className="storyboard-shot-thumb">
                    {src ? <img src={src} alt="" loading="lazy" /> : <FilmIcon size={18} />}
                  </div>
                  <div className="storyboard-shot-main">
                    <div className="storyboard-shot-head">
                      <span className="badge badge-mono">shot {shot.shot_index + 1}</span>
                      <TimestampChip timeMs={shot.start_ms} onSeek={onSeek} />
                      <span className="mono">{formatDuration(shot.duration_ms)}</span>
                      <span className="badge badge-violet">{shot.transition}</span>
                    </div>
                    <div className="storyboard-shot-grid">
                      <Field label="Type" value={shot.shot_type} />
                      <Field label="Motion" value={shot.camera_motion} />
                      <Field label="Beat" value={shot.emotional_beat} />
                      <Field label="Function" value={shot.narrative_function} />
                    </div>
                    {shot.on_screen_text.length ? (
                      <div className="storyboard-copy">
                        <span>Text</span>
                        <p>{shot.on_screen_text.join(" / ")}</p>
                      </div>
                    ) : null}
                    {shot.voiceover ? (
                      <div className="storyboard-copy">
                        <span>Voiceover</span>
                        <p>{shot.voiceover}</p>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value.replace(/_/g, " ")}</strong>
    </div>
  );
}
