"""Render an episode's production package into a real video with Google Veo (optionally Imagen first frames).

The package written by the video workflow (series/tap_<n>/goi_san_xuat.md) is read by code, not by a model:
each shot line ``**N.** IMG: ... VID: ...``, the shot durations from the shot table, the shared style line, and
the character tags (``[LINH-v1]``) expanded from the ``Appearance:`` lines of series/ho_so_nhan_vat.md.

Money safety: the first call (``confirmed`` false) only says what would be rendered and for how many seconds of
paid video. Only ``confirmed=true`` renders. Every started Veo operation is written to disk before it is polled,
so a re-run resumes it instead of paying again; finished clips are kept (checked, not just present).

Video is joined with ffmpeg into one file with the episode's subtitles as a subtitle track. When video cannot be
made (no Google sign-in, sign-in expired, no paid plan, quota, model not available) it stops at the first such
error and says so: the production package stays as it was, ready to paste into any video tool.
"""

from __future__ import annotations

import contextvars
import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Tuple

from agentdev.utils.function_catalog import ParamMeta

PACKAGE_FILE = "goi_san_xuat.md"
BIBLE_FILE = "ho_so_nhan_vat.md"
SUBTITLES_FILE = "loi_thoai_phu_de.md"
CLIPS_DIR = "video"
VEO_DURATIONS = (4, 6, 8)  # seconds Veo accepts
ASPECT_RATIOS = ("9:16", "16:9")
PARALLEL_SHOTS = 3
POLL_SECONDS = 10
SHOT_TIMEOUT_SECONDS = 15 * 60
RETRY_SECONDS = (30, 60, 120)  # waits before retrying a rate limit (429)
MIN_CLIP_BYTES = 1024

_SHOT_RE = re.compile(r"^\s*\*\*(\d+)\.\*\*\s*IMG:\s*(.*?)\s*VID:\s*(.+?)\s*$", re.MULTILINE)
_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|[^|\n]*\|\s*(\d+(?:[.,]\d+)?)\s*\|", re.MULTILINE)
_STYLE_RE = re.compile(r"^.*?Style(?: chung)?\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_TAG_RE = re.compile(r"\[([A-Z0-9_]+-v\d+)\]")
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_SRT_CUE_RE = re.compile(
    r"(?:^|\n)\s*(\d+)\s*\n(\d\d:\d\d:\d\d,\d{3}\s*-->\s*\d\d:\d\d:\d\d,\d{3})\s*\n(.+?)(?=\n\s*\n|\n```|\Z)",
    re.DOTALL,
)


class StopRendering(Exception):
    """An error no other shot can get past (sign-in, billing, quota, missing model): stop and keep the package."""


# --------------------------------------------------------------------------- reading the package

def _parse_package(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """(shared style, shots) from a production package; each shot has number, seconds, img and vid prompts."""
    style_match = _STYLE_RE.search(text)
    style = style_match.group(1).strip() if style_match else ""
    seconds = {int(n): float(s.replace(",", ".")) for n, s in _ROW_RE.findall(text)}
    shots = []
    for number, img, vid in _SHOT_RE.findall(text):
        n = int(number)
        shots.append({"number": n, "seconds": seconds.get(n, 6.0), "img": img.strip(), "vid": vid.strip()})
    shots.sort(key=lambda s: s["number"])
    return style, shots


def _parse_bible(text: str) -> Dict[str, str]:
    """Tag -> appearance, from heading tags followed by an ``Appearance:`` line, or both on one line."""
    looks: Dict[str, str] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        tags = _TAG_RE.findall(line)
        lowered = line.lower()
        if "appearance:" in lowered:
            look = line[lowered.index("appearance:") + len("appearance:"):]
            owner = tags[0] if tags else current
            if owner and look.strip():
                looks[owner] = look.strip().rstrip(".")
        elif tags and line.lstrip().startswith("#"):
            current = tags[0]
    return looks


def _expand_tags(prompt: str, looks: Dict[str, str]) -> str:
    """Replace each known [TAG] with its appearance (video models know nothing about our tags)."""
    return _TAG_RE.sub(lambda m: f"({looks[m.group(1)]})" if m.group(1) in looks else m.group(0), prompt)


def _veo_seconds(seconds: float) -> int:
    """The shortest duration Veo accepts that covers the shot (the clip is trimmed or held back to the shot)."""
    for allowed in VEO_DURATIONS:
        if seconds <= allowed:
            return allowed
    return VEO_DURATIONS[-1]


def _extract_srt(text: str) -> str:
    cues = _SRT_CUE_RE.findall(text)
    return "\n\n".join(f"{n}\n{times}\n{body.strip()}" for n, times, body in cues) + ("\n" if cues else "")


# --------------------------------------------------------------------------- Google client and errors

MEDIA_KEY_ENV = ("AGENTDEV_VEO_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
SETUP_HINT = ("Để tạo video: tạo API key ở Google AI Studio cho dự án đã bật thanh toán Gemini API (gói Google AI "
              "Pro chỉ mở Veo trong ứng dụng Gemini/Flow, không mở cho API), rồi đặt GEMINI_API_KEY trong tệp .env "
              "của AgentDev và khởi động lại máy chủ.")


def _gemini_client():
    """A google-genai client for Veo/Imagen, or StopRendering.

    A Gemini API key from the environment (paid Gemini API, only used for media) comes first: it is the usual way
    Veo is billed. Otherwise the user's Google Gemini sign-in from the Connections page is used.
    """
    from google import genai
    from google.genai import types
    from agentdev.connections.resolver import ConnectionResolutionError, resolve_connection
    from agentdev.connections.store import get_store
    from agentdev.runtime.node.agent.providers.gemini_provider import GeminiProvider, OAUTH_BEARER_PREFIX

    api_key = next((os.environ[name].strip() for name in MEDIA_KEY_ENV if os.environ.get(name, "").strip()), "")
    if api_key:
        return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120_000))

    connections = [c for c in get_store().list() if c.vendor == "gemini"]
    if not connections:
        raise StopRendering("chưa có API key Gemini trả phí và chưa kết nối tài khoản Google Gemini. " + SETUP_HINT)
    try:
        creds = resolve_connection(connections[0].id)
    except ConnectionResolutionError as exc:
        raise StopRendering(f"đăng nhập Google Gemini không dùng được: {exc}") from exc
    token = creds.token[len(OAUTH_BEARER_PREFIX):] if creds.token.startswith(OAUTH_BEARER_PREFIX) else creds.token
    if not token:
        raise StopRendering("đăng nhập Google Gemini không có quyền gọi API (hãy đăng nhập lại ở trang Kết nối)")
    options: Dict[str, Any] = {"headers": {"Authorization": f"Bearer {token}"}, "timeout": 120_000}
    if creds.base_url:
        options["base_url"] = creds.base_url
    # Same sign-in as the Gemini chat provider: Bearer token only, no API key header.
    client = genai.Client(api_key="oauth-placeholder", http_options=types.HttpOptions(**options))
    GeminiProvider._strip_api_key_header(client)
    return client


# Only account-level refusals end the whole run; a 429 is retried first, anything else fails just that shot.
_FATAL_WORDS = ("billing", "paid plan", "permission_denied", "unauthenticated", "insufficient", "failed_precondition")


def _is_rate_limit(exc: BaseException) -> bool:
    return getattr(exc, "code", None) == 429 or "resource_exhausted" in f"{getattr(exc, 'status', '')} {exc}".lower()


def _is_fatal(exc: BaseException) -> bool:
    """Errors every other shot would hit too: sign-in, billing/plan, missing model. (Rate limits: see _call.)"""
    if getattr(exc, "code", None) in (401, 403):
        return True
    text = f"{getattr(exc, 'status', '')} {exc}".lower()
    return any(word in text for word in _FATAL_WORDS)


def _call(fn, stop: threading.Event):
    """Run one Google API call; a rate limit waits and retries a few times, then is treated as fatal."""
    for wait in (*RETRY_SECONDS, None):
        try:
            return fn()
        except StopRendering:
            raise
        except Exception as exc:  # noqa: BLE001
            if not _is_rate_limit(exc):
                raise
            if wait is None or stop.is_set():
                raise StopRendering(f"Google giới hạn tốc độ/hạn mức: {str(exc)[:200]}") from exc
            time.sleep(wait)


def _pick_model(client, kind: str, override: str) -> str:
    if override:
        return override.removeprefix("models/")
    names = [str(m.name).removeprefix("models/") for m in client.models.list()]
    found = sorted((n for n in names if n.startswith(kind)), reverse=True)  # newest version first
    if not found:
        raise StopRendering(f"tài khoản chưa có model {kind} qua API. " + SETUP_HINT)
    best = [n for n in found if "fast" not in n] or found
    return best[0]


# --------------------------------------------------------------------------- rendering

def _valid_clip(path: Path) -> bool:
    """A finished mp4: big enough and starting with an ISO box header (a cut-off write fails this)."""
    try:
        if path.stat().st_size < MIN_CLIP_BYTES:
            return False
        with path.open("rb") as handle:
            return handle.read(12)[4:8] in (b"ftyp", b"moov", b"free", b"mdat", b"wide")
    except OSError:
        return False


def _shot_key(prompt: str, aspect_ratio: str, first_frame: bool) -> str:
    return hashlib.sha1(f"{prompt}|{aspect_ratio}|{first_frame}".encode("utf-8")).hexdigest()[:16]


def _write_atomic(path: Path, data: bytes) -> None:
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(data)
    os.replace(part, path)


def _render_shot(client, shot: Dict[str, Any], prompt: str, image_prompt: str, models: Dict[str, str],
                 aspect_ratio: str, out_dir: Path, stop: threading.Event,
                 cancel: Optional[threading.Event]) -> Dict[str, Any]:
    from google.genai import types

    number = shot["number"]
    stem = out_dir / f"shot_{number:02d}"
    clip, op_file, key_file, frame = (stem.with_suffix(".mp4"), stem.with_suffix(".op"),
                                      stem.with_suffix(".key"), stem.with_suffix(".png"))
    key = _shot_key(prompt, aspect_ratio, bool(models.get("imagen")))

    def halted() -> bool:
        return stop.is_set() or bool(cancel is not None and cancel.is_set())

    if clip.exists():
        same = (not key_file.exists()) or key_file.read_text(encoding="utf-8").strip() == key
        if _valid_clip(clip) and same:
            return {"number": number, "status": "kept", "path": clip}
        clip.unlink(missing_ok=True)  # cut off, or made for another prompt/ratio
        op_file.unlink(missing_ok=True)
        frame.unlink(missing_ok=True)
    if halted():
        return {"number": number, "status": "not_started"}
    try:
        operation = None
        if op_file.exists() and key_file.exists() and key_file.read_text(encoding="utf-8").strip() == key:
            # A paid operation from an earlier call that was never downloaded: resume it, do not pay again.
            operation = _call(lambda: client.operations.get(types.GenerateVideosOperation(
                name=op_file.read_text(encoding="utf-8").strip())), stop)
        if operation is None:
            image = None
            if models.get("imagen"):
                if frame.exists():
                    image = types.Image(image_bytes=frame.read_bytes(), mime_type="image/png")
                else:
                    result = _call(lambda: client.models.generate_images(
                        model=models["imagen"], prompt=image_prompt,
                        config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio=aspect_ratio)), stop)
                    if result.generated_images:
                        image = result.generated_images[0].image
                        if image.image_bytes:
                            _write_atomic(frame, image.image_bytes)
            config = types.GenerateVideosConfig(number_of_videos=1, aspect_ratio=aspect_ratio,
                                                duration_seconds=_veo_seconds(shot["seconds"]))
            operation = _call(lambda: client.models.generate_videos(
                model=models["veo"], prompt=prompt, image=image, config=config), stop)
            name = getattr(operation, "name", None)
            if name:  # billed from here on: remember it before polling
                key_file.write_text(key, encoding="utf-8")
                op_file.write_text(str(name), encoding="utf-8")
        deadline = time.monotonic() + SHOT_TIMEOUT_SECONDS
        while not operation.done:
            if halted():
                # Left running on Google's side and kept in the .op file: the next call resumes and downloads it.
                return {"number": number, "status": "not_started", "pending": True}
            if time.monotonic() > deadline:
                return {"number": number, "status": "failed", "pending": True,
                        "error": "hết thời gian chờ Veo (lần gọi sau sẽ nhận lại kết quả nếu đã xong)"}
            time.sleep(POLL_SECONDS)
            operation = _call(lambda: client.operations.get(operation), stop)
        if operation.error:
            op_file.unlink(missing_ok=True)
            return {"number": number, "status": "failed", "error": str(operation.error)[:200]}
        videos = getattr(operation.response, "generated_videos", None) or []
        if not videos or videos[0].video is None:
            op_file.unlink(missing_ok=True)
            return {"number": number, "status": "failed", "error": "Veo không trả video (có thể bị lọc nội dung)"}
        video = videos[0].video
        data = video.video_bytes or _call(lambda: client.files.download(file=video), stop)
        _write_atomic(clip, data)
        key_file.write_text(key, encoding="utf-8")
        op_file.unlink(missing_ok=True)
        return {"number": number, "status": "rendered", "path": clip}
    except StopRendering:
        stop.set()
        raise
    except Exception as exc:  # noqa: BLE001 - classified below, never hidden
        if _is_fatal(exc):
            stop.set()
            raise StopRendering(f"Google từ chối tạo video: {str(exc)[:300]}") from exc
        return {"number": number, "status": "failed", "error": str(exc)[:200]}


def _ffmpeg() -> Optional[str]:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def _probe(ffmpeg: str, clip: Path) -> Tuple[bool, float]:
    """(has an audio track, duration in seconds) of a clip."""
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(clip)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    match = _DURATION_RE.search(probe.stderr)
    seconds = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3)) if match else 0.0
    return "Audio:" in probe.stderr, seconds


def _assemble(ffmpeg: str, clips: List[Tuple[Path, float]], out_file: Path, srt: str) -> None:
    """Give each clip exactly its planned length (trim, or hold the last frame when Veo's clip is shorter, so the
    subtitle timeline stays aligned), give every clip an audio track, join them, add subtitles."""
    work = out_file.parent / "_ghep"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        parts = []
        for i, (clip, seconds) in enumerate(clips):
            part = work / f"part_{i:03d}.mp4"
            has_audio, actual = _probe(ffmpeg, clip)
            pad = max(0.0, seconds - actual) if actual else 0.0
            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip)]
            if has_audio:
                cmd += ["-map", "0:v:0", "-map", "0:a:0"]
            else:
                cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                        "-map", "0:v:0", "-map", "1:a:0"]
            if pad > 0.05:
                cmd += ["-vf", f"tpad=stop_mode=clone:stop_duration={pad + 0.1:.2f}"]
            cmd += ["-af", "apad", "-t", f"{seconds:.2f}", "-r", "24", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(part)]
            subprocess.run(cmd, check=True, capture_output=True)
            parts.append(part)
        listing = work / "list.txt"
        # Bare file names with cwd=work: no path (quotes, accents, backslashes) ever reaches the list.
        listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        joined = work / "joined.mp4"
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", "list.txt", "-c", "copy", "joined.mp4"], check=True, capture_output=True, cwd=str(work))
        result = work / "final.mp4"
        if srt:
            subs = out_file.with_suffix(".srt")
            subs.write_text(srt, encoding="utf-8")
            subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(joined), "-i", str(subs),
                            "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
                            "-metadata:s:s:0", "language=vie", str(result)], check=True, capture_output=True)
        else:
            shutil.move(str(joined), str(result))
        if out_file.exists():  # a complete earlier video is never lost to a partial re-run
            backup = out_file.with_name(out_file.stem + ".truoc" + out_file.suffix)
            os.replace(out_file, backup)
        os.replace(result, out_file)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _workspace(_context: Optional[Dict[str, Any]]) -> Path:
    root = (_context or {}).get("python_workspace_root")
    if not root:
        raise ValueError("python_workspace_root missing from _context")
    return Path(root).resolve()


def _episode_dir(root: Path, episode_dir: str) -> Path:
    if episode_dir:
        target = (root / episode_dir).resolve()
        if root not in target.parents and target != root:
            raise ValueError("episode_dir must be inside the project folder")
        return target
    found = sorted(root.glob(f"**/{PACKAGE_FILE}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not found:
        raise FileNotFoundError(f"không tìm thấy {PACKAGE_FILE} trong thư mục dự án")
    return found[0].parent


def _current_cancel_event() -> Optional[threading.Event]:
    try:
        from agentdev.runtime.node.agent.providers.cli_cancel import current_cancel_event
        return current_cancel_event()
    except Exception:  # noqa: BLE001 - outside a run there is nothing to cancel
        return None


def render_episode_video(
    episode_dir: Annotated[str, ParamMeta(
        description="Project-relative episode folder holding goi_san_xuat.md, e.g. series/tap_1. "
                    "Empty = the most recently updated production package")] = "",
    *,
    confirmed: Annotated[bool, ParamMeta(
        description="Must be true to spend money. False only returns what would be rendered and the paid seconds. "
                    "Pass true only when the user has already agreed to the cost")] = False,
    max_shots: Annotated[int, ParamMeta(description="Render only the first N shots (0 = all)")] = 0,
    aspect_ratio: Annotated[str, ParamMeta(description="9:16 (vertical) or 16:9")] = "9:16",
    use_first_frame: Annotated[bool, ParamMeta(
        description="Make a first frame with Imagen from the IMG prompt, then animate it with Veo "
                    "(steadier characters)")] = True,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Turn an episode production package into a video with Google Veo (paid). Call it ONCE per episode.

    Without confirmed=true it only reports the shots and paid seconds. Finished shots are kept, started ones are
    resumed, so a re-run never pays twice. If video cannot be made (no sign-in, no paid plan, quota), returns
    status "not_rendered" with the reason; the production package is unchanged.
    """
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(f"aspect_ratio must be one of {', '.join(ASPECT_RATIOS)}")
    root = _workspace(_context)
    folder = _episode_dir(root, episode_dir)
    package = folder / PACKAGE_FILE
    if not package.exists():
        raise FileNotFoundError(f"{package.relative_to(root).as_posix()} không tồn tại")
    style, shots = _parse_package(package.read_text(encoding="utf-8"))
    if not shots:
        raise ValueError("gói sản xuất không có dòng shot dạng '**N.** IMG: ... VID: ...'")
    if max_shots > 0:
        shots = shots[:max_shots]
    bible = next((p for p in (folder.parent / BIBLE_FILE, root / "series" / BIBLE_FILE) if p.exists()), None)
    looks = _parse_bible(bible.read_text(encoding="utf-8")) if bible else {}
    rel = folder.relative_to(root).as_posix()
    fallback = f"Gói sản xuất trong {rel}/ vẫn giữ nguyên, có thể dán câu lệnh vào công cụ video."
    out_dir = folder / CLIPS_DIR

    if not confirmed:
        to_pay = [s for s in shots if not _valid_clip(out_dir / f"shot_{s['number']:02d}.mp4")]
        return {"status": "needs_confirmation", "shots_total": len(shots),
                "shots_already_rendered": len(shots) - len(to_pay), "shots_to_render": len(to_pay),
                "seconds_of_video_to_pay": sum(_veo_seconds(s["seconds"]) for s in to_pay),
                "note": "Chưa tạo gì và chưa tốn tiền. Gọi lại với confirmed=true khi người dùng đã đồng ý chi phí."}

    results: List[Dict[str, Any]] = []
    try:
        client = _gemini_client()
        models = {"veo": _pick_model(client, "veo", os.environ.get("AGENTDEV_VEO_MODEL", ""))}
        if use_first_frame:
            try:
                models["imagen"] = _pick_model(client, "imagen", os.environ.get("AGENTDEV_IMAGEN_MODEL", ""))
            except StopRendering:
                pass  # no Imagen: Veo renders from the text prompt alone
        out_dir.mkdir(exist_ok=True)  # only once video can really be made: no empty folder otherwise
        stop = threading.Event()
        cancel = _current_cancel_event()  # a ContextVar: read here, the pool threads would not see it
        lead = f"{style}. " if style else ""

        def job(shot):
            prompt = f"{lead}{_expand_tags(shot['img'], looks)} Motion: {_expand_tags(shot['vid'], looks)}"
            image_prompt = f"{lead}{_expand_tags(shot['img'], looks)}"
            return _render_shot(client, shot, prompt, image_prompt, models, aspect_ratio, out_dir, stop, cancel)

        with ThreadPoolExecutor(max_workers=PARALLEL_SHOTS) as pool:
            futures = [pool.submit(contextvars.copy_context().run, job, shot) for shot in shots]
            errors: List[StopRendering] = []
            for future in futures:
                try:
                    results.append(future.result())
                except StopRendering as exc:
                    errors.append(exc)
            if errors and not results:
                raise errors[0]
    except StopRendering as exc:
        made = len(list(out_dir.glob("shot_*.mp4"))) if out_dir.exists() else 0
        return {"status": "not_rendered", "reason": str(exc), "clips_kept": made,
                "clips_folder": f"{rel}/{CLIPS_DIR}", "note": fallback}

    by_number = {r["number"]: r for r in results}
    ready = [(by_number[s["number"]]["path"], float(s["seconds"])) for s in shots
             if by_number.get(s["number"], {}).get("status") in ("rendered", "kept")]
    failed = [{"shot": r["number"], "error": r.get("error", r["status"])} for r in results
              if r["status"] not in ("rendered", "kept")]
    summary: Dict[str, Any] = {
        "shots_total": len(shots),
        "shots_rendered_now": sum(r["status"] == "rendered" for r in results),
        "shots_kept_from_before": sum(r["status"] == "kept" for r in results),
        "shots_failed": failed,
        "shots_pending_on_google": [r["number"] for r in results if r.get("pending")],
        "seconds_of_video_paid": sum(_veo_seconds(s["seconds"]) for s in shots
                                     if by_number.get(s["number"], {}).get("status") == "rendered"),
        "model": models,
        "clips_folder": f"{rel}/{CLIPS_DIR}",
    }
    if not ready:
        return {"status": "not_rendered", "reason": "không shot nào tạo được", **summary, "note": fallback}
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return {"status": "clips_only", "reason": "không có ffmpeg để ghép các clip", **summary}
    final = folder / f"{folder.name}.mp4"
    srt_source = folder / SUBTITLES_FILE
    srt = _extract_srt(srt_source.read_text(encoding="utf-8")) if srt_source.exists() else ""
    try:
        _assemble(ffmpeg, ready, final, srt)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace")[-300:]
        return {"status": "clips_only", "reason": f"ghép video lỗi: {detail}", **summary}
    status = "rendered" if not failed else "partial"
    return {"status": status, "video": final.relative_to(root).as_posix(), "subtitles": bool(srt), **summary}
