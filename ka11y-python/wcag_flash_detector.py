#!/usr/bin/env python3
"""
⚡ WCAG 2.3.1 — Three Flashes or Below Threshold
Automated Photosensitive Epilepsy Flash Detection

Criterion: No content shall flash more than 3 times per second, or the flash must be below the Harding FPA general / red flash thresholds.

Pipeline:
1. Launch browser → record 10s video of target page
2. Extract frames at 60 fps via OpenCV
3. Compute per-pixel luminance delta in 1-second sliding windows
4. Identify flash candidate regions (>10% luma range change, >25% of 10° foveal zone)
5. Count flash pairs — fail if >3/s
6. Red-flash check: hue boundary crossing with saturation filter
7. Emit structured Rich report
"""

from __future__ import annotations

import asyncio
import colorsys
import math
import os
import time
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import matplotlib.pyplot as plt
from pydantic import BaseModel, Field, computed_field
from rich.console import Console
from rich.live import Live
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import print as rprint
from scipy.signal import find_peaks
from playwright.async_api import async_playwright

# ── Rich Console (single global instance) ─────────────────────────────────────
console = Console(highlight=True, markup=True)

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger("wcag231")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
class AnalysisConfig(BaseModel):
    """All knobs for the WCAG 2.3.1 analysis pipeline."""

    # Target
    url: str = Field(
        default="https://1minus1.com/",
        description="Page to analyse (known flashing test page).",
    )
    record_seconds: int = Field(10, ge=3, le=30, description="Recording duration (s).")

    # Browser viewport
    viewport_width: int = 1280
    viewport_height: int = 720

    # Video / frame
    fps: int = Field(60, description="Frame extraction rate.")
    output_dir: Path = Field(Path("wcag231_output"), description="Where to write artefacts.")

    # Flash thresholds  (Harding FPA / W3C)
    luma_change_threshold: float = Field(
        0.10, description="Min luminance delta fraction (10% of 255 ≈ 25 luma units)."
    )
    flash_per_second_limit: int = Field(3, description="Max allowed flash pairs per second.")
    foveal_area_fraction: float = Field(
        0.25, description="Min fraction of 10° foveal zone that must be affected."
    )

    # Red-flash
    red_hue_low: int = Field(0,   description="Lower red hue bound (HSV 0-180 in OpenCV).")
    red_hue_high_lower: int = Field(10,  description="Upper edge of lower red band.")
    red_hue_high_upper: int = Field(170, description="Lower edge of upper red band.")
    red_saturation_min: float = Field(0.5, description="Min saturation to count as red.")

    @computed_field  # type: ignore[misc]
    @property
    def luma_delta_units(self) -> float:
        return self.luma_change_threshold * 255

    @computed_field  # type: ignore[misc]
    @property
    def foveal_pixel_count(self) -> int:
        """Pixels in the 10° visual-angle zone at 68 cm from a 24" 1080p monitor."""
        total = self.viewport_width * self.viewport_height
        return int(total * 0.25)   # 25% of frame ≈ 10° foveal region


# ─────────────────────────────────────────────────────────────────────────────
# RESULT MODELS
# ─────────────────────────────────────────────────────────────────────────────
class WindowResult(BaseModel):
    window_index: int
    start_sec: float
    end_sec: float
    flash_count: int
    affected_pixels: int
    foveal_threshold_pixels: int
    general_flash_fail: bool
    red_flash_count: int
    red_flash_fail: bool

    @computed_field  # type: ignore[misc]
    @property
    def any_fail(self) -> bool:
        return self.general_flash_fail or self.red_flash_fail


class AnalysisReport(BaseModel):
    url: str
    config: AnalysisConfig
    total_frames: int
    actual_fps: float
    duration_seconds: float
    windows: List[WindowResult]
    overall_pass: bool
    failure_reasons: List[str]
    peak_flash_rate: float
    peak_red_flash_rate: float
    video_path: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

async def record_page_video(config: AnalysisConfig) -> Path:
    """
    Launch headless Chromium, navigate to `config.url`,
    capture screenshots at target FPS for `record_seconds`,
    stitch into an MP4 via OpenCV VideoWriter.
    Returns path to the output .mp4.
    """
    video_path = config.output_dir / "recorded_page.mp4"
    frames_dir = config.output_dir / "raw_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    console.print(Rule("[bold cyan]Step 1 — Browser Recording[/bold cyan]"))
    log.info("Launching Playwright Chromium (headless)")

    frame_paths: List[Path] = []
    total_frames = config.record_seconds * config.fps
    interval = 1.0 / config.fps

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )
        page = await browser.new_page(
            viewport={"width": config.viewport_width, "height": config.viewport_height}
        )
        log.info(f"Navigating to {config.url}")
        try:
            await page.goto(config.url, timeout=20_000, wait_until="domcontentloaded")
        except Exception as e:
            log.warning(f"Page load error (continuing anyway): {e}")

        await asyncio.sleep(0.5)  # allow JS animations to start
        log.info(f"Recording {total_frames} frames ({config.record_seconds}s @ {config.fps} fps)")

        with progress:
            task = progress.add_task("📷 Capturing frames", total=total_frames)
            for i in range(total_frames):
                t0 = time.perf_counter()
                frame_path = frames_dir / f"frame_{i:06d}.png"
                await page.screenshot(path=str(frame_path), full_page=False)
                frame_paths.append(frame_path)
                elapsed = time.perf_counter() - t0
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                progress.advance(task)

        await browser.close()

    log.info(f"Captured {len(frame_paths)} frames → stitching MP4")

    # Stitch into video
    sample = cv2.imread(str(frame_paths[0]))
    h, w = sample.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, config.fps, (w, h))
    for fp in frame_paths:
        frame = cv2.imread(str(fp))
        writer.write(frame)
        # Optional: remove raw frames after stitching
        # fp.unlink()
    writer.release()

    log.info(f"Video saved → [cyan]{video_path}[/cyan] ({video_path.stat().st_size/1024:.1f} KB)")
    return video_path


def extract_frames(video_path: Path, target_fps: int) -> Tuple[np.ndarray, float]:
    """
    Read video and extract frames at `target_fps`.
    Returns:
        frames  : np.ndarray  shape (N, H, W, 3)  uint8 BGR
        actual_fps : float
    """
    console.print(Rule("[bold cyan]Step 2 — Frame Extraction[/bold cyan]"))
    cap = cv2.VideoCapture(str(video_path))
    source_fps = cap.get(cv2.CAP_PROP_FPS) or target_fps
    total_src  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(source_fps / target_fps))

    log.info(f"Video FPS: {source_fps:.1f} | Total frames in file: {total_src} | Step: {step}")

    frames: List[np.ndarray] = []
    idx = 0
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    with progress:
        task = progress.add_task("🎞️  Reading frames", total=total_src // step)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % step == 0:
                frames.append(frame)
                progress.advance(task)
            idx += 1
    cap.release()

    actual_fps = source_fps / step
    log.info(f"Extracted {len(frames)} frames at effective {actual_fps:.1f} fps")
    return np.array(frames, dtype=np.uint8), actual_fps


def compute_luminance_stack(frames: np.ndarray) -> np.ndarray:
    """
    Convert BGR stack → relative luminance (0-255) per frame.
    Uses ITU-R BT.709 coefficients: L = 0.2126R + 0.7152G + 0.0722B
    Returns float32 array shape (N, H, W).
    """
    console.print(Rule("[bold cyan]Step 3 — Luminance Stack Computation[/bold cyan]"))
    log.info(f"Input shape: {frames.shape}  dtype: {frames.dtype}")

    rgb = frames[:, :, :, ::-1].astype(np.float32)  # BGR→RGB
    # BT.709
    luma = (0.2126 * rgb[:, :, :, 0]
          + 0.7152 * rgb[:, :, :, 1]
          + 0.0722 * rgb[:, :, :, 2])
    log.info(f"Luminance stack shape: {luma.shape}  min={luma.min():.1f}  max={luma.max():.1f}")
    return luma


def detect_flash_events(
    luma_stack: np.ndarray,
    frames_bgr: np.ndarray,
    actual_fps: float,
    config: AnalysisConfig,
) -> List[WindowResult]:
    """
    Slide a 1-second window over luma_stack.
    For each window:
      1. Compute per-pixel luma delta between consecutive frames
      2. Identify 'flash candidate' pixels: delta > luma_change_threshold
      3. Check if candidate region > foveal_pixel_count
      4. Count direction reversals (rise→fall or fall→rise) = flash pairs
      5. Red-flash check on HSV of candidate pixels
    Returns list of WindowResult.
    """
    console.print(Rule("[bold cyan]Step 4 — Flash Event Detection[/bold cyan]"))

    frames_per_window = int(actual_fps)  # 1-second window
    total_frames = luma_stack.shape[0]
    results: List[WindowResult] = []

    luma_threshold = config.luma_delta_units
    foveal_threshold = config.foveal_pixel_count

    log.info(
        f"Window size: {frames_per_window} frames | "
        f"Luma threshold: {luma_threshold:.1f} | "
        f"Foveal threshold: {foveal_threshold:,} px"
    )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    n_windows = max(1, total_frames - frames_per_window + 1)

    with progress:
        task = progress.add_task("🔍 Sliding window analysis", total=n_windows)

        for win_idx in range(n_windows):
            w_start = win_idx
            w_end   = min(win_idx + frames_per_window, total_frames)
            window_luma = luma_stack[w_start:w_end]    # (W, H, W)
            window_bgr  = frames_bgr[w_start:w_end]    # (W, H, W, 3)

            start_sec = win_idx / actual_fps
            end_sec   = w_end   / actual_fps

            # ── Per-pixel luminance delta ──────────────────────────────────
            # deltas[i] = luma[i+1] - luma[i], shape (frames-1, H, W)
            deltas = np.diff(window_luma, axis=0)      # signed

            # Flash mask: |delta| > threshold over *any* frame transition
            flash_mask = np.any(np.abs(deltas) > luma_threshold, axis=0)  # (H, W) bool
            affected_pixels = int(flash_mask.sum())

            log.debug(
                f"Window {win_idx:04d} [{start_sec:.2f}s–{end_sec:.2f}s] "
                f"affected_px={affected_pixels:,} / foveal={foveal_threshold:,}"
            )

            # ── Flash counting (reversals) ─────────────────────────────────
            if affected_pixels > 0:
                region_mean_luma = window_luma[:, flash_mask].mean(axis=1)  # (frames,)
                # Count sign changes in first derivative → direction reversals
                diff_sign = np.sign(np.diff(region_mean_luma))
                diff_sign = diff_sign[diff_sign != 0]   # drop zeros
                sign_changes = np.sum(np.diff(diff_sign) != 0)
                # Each flash pair = 1 rising edge + 1 falling edge = 2 sign changes
                flash_count = sign_changes // 2
            else:
                flash_count = 0

            general_fail = (
                flash_count > config.flash_per_second_limit
                and affected_pixels > foveal_threshold
            )

            # ── Red-flash check ───────────────────────────────────────────
            red_flash_count = 0
            if affected_pixels > 0:
                red_flash_count = _count_red_flashes(
                    window_bgr, flash_mask, deltas, luma_threshold, config
                )
            red_fail = red_flash_count > config.flash_per_second_limit

            if general_fail or red_fail:
                status = "[bold red]FAIL[/bold red]"
            else:
                status = "[green]PASS[/green]"

            log.info(
                f"Win {win_idx:04d} | {start_sec:.2f}–{end_sec:.2f}s | "
                f"flashes={flash_count} red={red_flash_count} "
                f"affected={affected_pixels:,}px → {status}"
            )

            results.append(WindowResult(
                window_index=win_idx,
                start_sec=round(start_sec, 3),
                end_sec=round(end_sec, 3),
                flash_count=int(flash_count),
                affected_pixels=affected_pixels,
                foveal_threshold_pixels=foveal_threshold,
                general_flash_fail=general_fail,
                red_flash_count=int(red_flash_count),
                red_flash_fail=red_fail,
            ))

            progress.advance(task)

    return results


def _count_red_flashes(
    window_bgr: np.ndarray,
    flash_mask: np.ndarray,
    deltas: np.ndarray,
    luma_threshold: float,
    config: AnalysisConfig,
) -> int:
    """
    Within the flash-candidate region, count frames where:
      - Dominant hue is in red range (HSV H < 10° or H > 170° in OpenCV 0-180)
      - Saturation > red_saturation_min
      - AND a significant luma transition occurred
    Returns approximate red-flash pairs per window.
    """
    red_frames: List[bool] = []

    for frame_bgr in window_bgr:
        region = frame_bgr[flash_mask]   # (N_px, 3)
        if region.size == 0:
            red_frames.append(False)
            continue
        hsv = cv2.cvtColor(region.reshape(1, -1, 3), cv2.COLOR_BGR2HSV)
        h = hsv[0, :, 0].astype(float)   # 0-180 in OpenCV
        s = hsv[0, :, 1].astype(float) / 255.0

        is_red_hue = (h <= config.red_hue_high_lower) | (h >= config.red_hue_high_upper)
        is_saturated = s >= config.red_saturation_min
        red_pixel_fraction = (is_red_hue & is_saturated).mean()
        red_frames.append(red_pixel_fraction > 0.1)   # >10% of region is red

    # Count sign changes in red_frames boolean series
    rf = np.array(red_frames, dtype=int)
    transitions = np.sum(np.diff(rf) != 0)
    return transitions // 2


def build_report(
    window_results: List[WindowResult],
    config: AnalysisConfig,
    total_frames: int,
    actual_fps: float,
    duration_seconds: float,
    video_path: Optional[Path] = None,
) -> AnalysisReport:
    failure_reasons: List[str] = []
    peak_flash = max((w.flash_count for w in window_results), default=0)
    peak_red   = max((w.red_flash_count for w in window_results), default=0)

    gen_fails = [w for w in window_results if w.general_flash_fail]
    red_fails = [w for w in window_results if w.red_flash_fail]

    if gen_fails:
        failure_reasons.append(
            f"General flash: {len(gen_fails)} window(s) exceeded "
            f"{config.flash_per_second_limit} flashes/s with "
            f">{config.foveal_pixel_count:,} pixels affected"
        )
    if red_fails:
        failure_reasons.append(
            f"Red flash: {len(red_fails)} window(s) exceeded "
            f"{config.flash_per_second_limit} red flashes/s"
        )

    return AnalysisReport(
        url=config.url,
        config=config,
        total_frames=total_frames,
        actual_fps=round(actual_fps, 2),
        duration_seconds=round(duration_seconds, 2),
        windows=window_results,
        overall_pass=not bool(failure_reasons),
        failure_reasons=failure_reasons,
        peak_flash_rate=float(peak_flash),
        peak_red_flash_rate=float(peak_red),
        video_path=str(video_path) if video_path else None,
    )


def print_rich_report(report: AnalysisReport) -> None:
    console.print(Rule("[bold magenta]WCAG 2.3.1 — Final Report[/bold magenta]"))

    # Summary panel
    verdict_text = (
        "[bold red]❌ FAIL[/bold red]" if not report.overall_pass
        else "[bold green]✅ PASS[/bold green]"
    )
    summary_lines = [
        f"[bold]URL:[/bold]         [cyan]{report.url}[/cyan]",
        f"[bold]Verdict:[/bold]     {verdict_text}",
        f"[bold]Duration:[/bold]    {report.duration_seconds}s  ({report.total_frames} frames @ {report.actual_fps} fps)",
        f"[bold]Peak flash:[/bold]  {report.peak_flash_rate:.0f} /s  (limit: {report.config.flash_per_second_limit}/s)",
        f"[bold]Peak red:[/bold]    {report.peak_red_flash_rate:.0f} red flash/s",
    ]
    if report.failure_reasons:
        summary_lines.append("")
        summary_lines.append("[bold red]Failure reasons:[/bold red]")
        for r in report.failure_reasons:
            summary_lines.append(f"  • {r}")

    console.print(Panel(
        "\n".join(summary_lines),
        title="[bold]Summary[/bold]",
        border_style="red" if not report.overall_pass else "green",
        padding=(1, 2),
    ))

    # Per-window table (show only first 30 for readability)
    console.print(Rule("[bold]Per-Window Results (first 30)[/bold]"))
    tbl = Table(
        show_header=True,
        header_style="bold magenta",
        border_style="grey50",
        row_styles=["none", "dim"],
    )
    tbl.add_column("Win",    justify="right",  width=5)
    tbl.add_column("Start",  justify="right",  width=7)
    tbl.add_column("End",    justify="right",  width=7)
    tbl.add_column("Flashes",justify="right",  width=8)
    tbl.add_column("Red",    justify="right",  width=6)
    tbl.add_column("Affected px", justify="right", width=12)
    tbl.add_column("General",justify="center", width=9)
    tbl.add_column("Red",    justify="center", width=9)

    for w in report.windows[:30]:
        gen_str = "[red]FAIL[/red]" if w.general_flash_fail else "[green]pass[/green]"
        red_str = "[red]FAIL[/red]" if w.red_flash_fail else "[green]pass[/green]"
        tbl.add_row(
            str(w.window_index),
            f"{w.start_sec:.2f}s",
            f"{w.end_sec:.2f}s",
            str(w.flash_count),
            str(w.red_flash_count),
            f"{w.affected_pixels:,}",
            gen_str,
            red_str,
        )

    console.print(tbl)
    if len(report.windows) > 30:
        console.print(f"[dim]… and {len(report.windows)-30} more windows (see JSON report)[/dim]")


def visualise_results(report: AnalysisReport, actual_fps: float) -> Path:
    """Uses Matplotlib to generate a flash timeline chart."""
    console.print(Rule("[bold cyan]Step 5 — Flash Timeline Visualisation[/bold cyan]"))

    times       = [w.start_sec for w in report.windows]
    flash_rates = [w.flash_count for w in report.windows]
    red_rates   = [w.red_flash_count for w in report.windows]
    colors      = ["#e74c3c" if w.any_fail else "#2ecc71" for w in report.windows]

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.patch.set_facecolor("#1a1a2e")
    for ax in axes:
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="#ccc")
        ax.spines[["top", "right"]].set_visible(False)
        for spine in ax.spines.values():
            spine.set_color("#444")

    # ── Flash count per window ────────────────────────────────────────────────────
    axes[0].bar(times, flash_rates, width=1/actual_fps*0.9, color=colors, alpha=0.9)
    axes[0].axhline(report.config.flash_per_second_limit, color="#f39c12", lw=1.5, ls="--", label="Limit (3/s)")
    axes[0].set_ylabel("Flash pairs/s", color="#ccc")
    axes[0].set_title("General Flash Rate per Sliding Window", color="white", pad=8)
    axes[0].legend(facecolor="#222", edgecolor="#555", labelcolor="white")

    # ── Red flash count ───────────────────────────────────────────────────────────
    axes[1].bar(times, red_rates, width=1/actual_fps*0.9, color="#e74c3c", alpha=0.8)
    axes[1].axhline(report.config.flash_per_second_limit, color="#f39c12", lw=1.5, ls="--")
    axes[1].set_ylabel("Red flash/s", color="#ccc")
    axes[1].set_title("Red Flash Rate per Sliding Window", color="white", pad=8)

    # ── Affected pixel count ──────────────────────────────────────────────────────
    affected = [w.affected_pixels for w in report.windows]
    axes[2].fill_between(times, affected, color="#9b59b6", alpha=0.6, step="mid")
    axes[2].axhline(report.config.foveal_pixel_count, color="#f39c12", lw=1.5, ls="--", label="Foveal threshold")
    axes[2].set_ylabel("Affected px", color="#ccc")
    axes[2].set_xlabel("Time (s)", color="#ccc")
    axes[2].set_title("Affected Pixel Count (flash candidates)", color="white", pad=8)
    axes[2].legend(facecolor="#222", edgecolor="#555", labelcolor="white")

    # Fail patches
    for w in report.windows:
        if w.any_fail:
            for ax in axes:
                ax.axvspan(w.start_sec, w.end_sec, color="red", alpha=0.08)

    verdict = "FAIL ❌" if not report.overall_pass else "PASS ✅"
    fig.suptitle(
        f"WCAG 2.3.1 Flash Analysis — {verdict}",
        color="white", fontsize=14, fontweight="bold", y=0.98
    )
    plt.tight_layout()
    chart_path = report.config.output_dir / "flash_timeline.png"
    fig.savefig(chart_path, dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    log.info(f"Chart saved → {chart_path}")
    return chart_path


def save_json_report(report: AnalysisReport, output_dir: Path) -> Path:
    console.print(Rule("[bold cyan]Step 6 — Persist JSON Report[/bold cyan]"))
    json_path = output_dir / "wcag231_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)
    log.info(f"JSON report written → {json_path}  ({json_path.stat().st_size/1024:.1f} KB)")
    return json_path


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="WCAG 2.3.1 Flash Detector")
    parser.add_argument("--url", nargs="?", help="Target URL to analyse")
    args = parser.parse_args()

    # Final configuration (Defaults or CLI arg)
    cfg = AnalysisConfig(url=args.url) if args.url else AnalysisConfig()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        "[bold yellow]WCAG 2.3.1[/bold yellow] Flash Detector — Starting Pipeline",
        border_style="yellow",
    ))

    console.print(Panel(
        f"[bold]Target URL:[/bold] [cyan]{cfg.url}[/cyan]\n"
        f"[bold]Record duration:[/bold] {cfg.record_seconds}s at [green]{cfg.fps}[/green] fps\n"
        f"[bold]Luma threshold:[/bold] {cfg.luma_change_threshold*100:.0f}% → {cfg.luma_delta_units:.1f} luma units\n"
        f"[bold]Flash limit:[/bold] {cfg.flash_per_second_limit} flashes/s\n"
        f"[bold]Foveal zone pixels:[/bold] {cfg.foveal_pixel_count:,}\n"
        f"[bold]Output dir:[/bold] {cfg.output_dir.resolve()}",
        title="[yellow]⚙️  Analysis Config[/yellow]",
        border_style="bright_blue",
    ))
    log.info("Config validated — all fields OK")

    # 1. Record
    video_path = await record_page_video(cfg)
    console.print(f"\n[bold green]✅ Recording complete:[/bold green] {video_path}")

    # 2. Extract
    frames, actual_fps = extract_frames(video_path, cfg.fps)

    # 3. Compute Luminance
    luma_stack = compute_luminance_stack(frames)
    duration_sec = len(frames) / actual_fps

    table = Table(title="Frame Stats", border_style="bright_blue")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan")
    table.add_row("Total frames", str(len(frames)))
    table.add_row("Actual FPS", f"{actual_fps:.1f}")
    table.add_row("Duration", f"{duration_sec:.2f}s")
    table.add_row("Frame shape (H×W)", f"{frames.shape[1]}×{frames.shape[2]}")
    table.add_row("Luma range", f"{luma_stack.min():.1f} – {luma_stack.max():.1f}")
    console.print(table)

    # 4. Detect Flash Events
    window_results = detect_flash_events(luma_stack, frames, actual_fps, cfg)
    console.print(f"\n[bold]Windows analysed:[/bold] {len(window_results)}")

    # 5. Build Report
    report = build_report(
        window_results=window_results,
        config=cfg,
        total_frames=len(frames),
        actual_fps=actual_fps,
        duration_seconds=duration_sec,
        video_path=video_path,
    )

    # 6. Output Report
    print_rich_report(report)

    # 7. Visualise
    chart_path = visualise_results(report, actual_fps)

    # 8. Save JSON
    json_path = save_json_report(report, cfg.output_dir)

    console.print(Panel(
        f"[bold]Video:[/bold]  {video_path}\n"
        f"[bold]Chart:[/bold]  {chart_path}\n"
        f"[bold]JSON:[/bold]   {json_path}",
        title="[yellow]📁 Output Files[/yellow]",
        border_style="yellow",
    ))

    # Final verdict
    if report.overall_pass:
        console.print(Panel(
            "[bold green]✅ WCAG 2.3.1 PASS[/bold green]\nNo flashing content exceeded the Harding FPA thresholds.",
            border_style="green",
        ))
    else:
        reasons_str = "\n".join(f"  • {r}" for r in report.failure_reasons)
        console.print(Panel(
            f"[bold red]❌ WCAG 2.3.1 FAIL[/bold red]\n\n{reasons_str}",
            border_style="red",
            padding=(1, 2),
        ))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Process interrupted by user")
    except Exception as e:
        log.exception(f"Fatal error: {e}")
