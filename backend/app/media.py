"""Thin FFmpeg/ffprobe helpers."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import env


class FFmpegError(Exception):
    pass


def run(args: list[str], *, input_bytes: bytes | None = None, timeout: int = 3600) -> str:
    cmd = [env.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", *args]
    p = subprocess.run(cmd, input=input_bytes, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise FFmpegError(f"ffmpeg failed ({p.returncode}): {p.stderr.decode(errors='ignore')[-2000:]}\n"
                          f"cmd: {' '.join(cmd)[:1500]}")
    return p.stderr.decode(errors="ignore")


def run_capture_stderr(args: list[str], timeout: int = 3600) -> str:
    """For analysis filters (blackdetect, silencedetect, ebur128) that log to stderr."""
    cmd = [env.ffmpeg_bin, "-hide_banner", "-nostats", "-y", *args]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return p.stderr.decode(errors="ignore")


def probe(path: str | Path) -> dict:
    p = subprocess.run([env.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                        str(path)], capture_output=True, timeout=120)
    if p.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path}: {p.stderr.decode(errors='ignore')}")
    return json.loads(p.stdout)


def duration(path: str | Path) -> float:
    return float(probe(path)["format"]["duration"])


class FramePipe:
    """Stream raw RGB frames (e.g. from Pillow) into an H.264 encoder."""

    def __init__(self, out: Path, w: int, h: int, fps: int, preset: str = "veryfast", crf: int = 18):
        self.proc = subprocess.Popen(
            [env.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
             "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, img) -> None:
        self.proc.stdin.write(img.tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="ignore")
        if self.proc.wait() != 0:
            raise FFmpegError(f"frame encode failed: {err[-1500:]}")
