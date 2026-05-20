from __future__ import annotations

import shutil
from pathlib import Path

from ad_classifier.config import resolve_config_path


def cleanup_ad_artifacts(config, config_file: Path, ad_id: str, source_path: str | None) -> list[str]:
    roots = [
        resolve_config_path(config.paths.uploads, config_file),
        resolve_config_path(config.paths.frames, config_file),
        resolve_config_path(config.paths.audio, config_file),
        resolve_config_path(config.paths.whisper, config_file),
        resolve_config_path(config.paths.out, config_file),
    ]
    targets = [
        roots[1] / ad_id,
        roots[2] / ad_id,
        roots[3] / ad_id,
        roots[4] / ad_id,
    ]
    if source_path:
        targets.append(Path(source_path))

    removed: list[str] = []
    for target in targets:
        resolved = target.expanduser().resolve()
        if not any(_is_relative_to(resolved, root.expanduser().resolve()) for root in roots):
            continue
        if resolved.is_dir():
            shutil.rmtree(resolved)
            removed.append(str(resolved))
        elif resolved.exists():
            resolved.unlink()
            removed.append(str(resolved))
    return removed


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
