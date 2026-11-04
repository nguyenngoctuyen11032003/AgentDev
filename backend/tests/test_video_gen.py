"""render_episode_video: package parsing, cost safety and the full clip -> video path, with a fake Google client."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from functions.function_calling import video_gen

PACKAGE = """Replace each tag with its Appearance line from the bible when generating.

# GÓI SẢN XUẤT - Tập 1
Tổng: 3 cảnh quay. Style chung: photorealistic, cinematic, 9:16 vertical.

## Danh sách shot
| # | Giây | Thời lượng | Khung hình |
|---|------|-----------|-----------|
| 1 | 0-5 | 5 | ECU |
| 2 | 5-11 | 6 | MS |
| 3 | 11-14 | 3 | CU |

## Prompt từng shot
**1.** IMG: Close-up of [LINH-v1] waking up. VID: Handheld jolt.

**2.** IMG: [LINH-v1] facing [HETHONG-v1] in a dark room. VID: Slow push-in.

**3.** IMG: A desk with a photo. VID: Rack focus.
"""

BIBLE = """# Hồ sơ
## TRẦN NGỌC LINH [LINH-v1]
- Tuổi: 28
- Appearance: Vietnamese woman, 28, grey hoodie.
## HỆ THỐNG [HETHONG-v1]
- Appearance: translucent cyan holographic panel.
[NVGD-v1] Bank teller - Appearance: woman in her 30s, white blouse.
"""

SUBS = """# Lời thoại
```
1
00:00:00,000 --> 00:00:02,000
Cảnh báo.

2
00:00:02,500 --> 00:00:04,000
Mình mơ à?
```
"""


def _project(tmp_path):
    episode = tmp_path / "series" / "tap_1"
    episode.mkdir(parents=True)
    (episode / "goi_san_xuat.md").write_text(PACKAGE, encoding="utf-8")
    (episode / "loi_thoai_phu_de.md").write_text(SUBS, encoding="utf-8")
    (tmp_path / "series" / "ho_so_nhan_vat.md").write_text(BIBLE, encoding="utf-8")
    return {"python_workspace_root": str(tmp_path)}


def test_package_bible_and_subtitles_are_read_without_a_model():
    style, shots = video_gen._parse_package(PACKAGE)
    assert style.startswith("photorealistic") and [s["number"] for s in shots] == [1, 2, 3]
    assert [s["seconds"] for s in shots] == [5, 6, 3]
    looks = video_gen._parse_bible(BIBLE)
    assert looks == {"LINH-v1": "Vietnamese woman, 28, grey hoodie", "HETHONG-v1": "translucent cyan holographic panel",
                     "NVGD-v1": "woman in her 30s, white blouse"}
    assert video_gen._expand_tags(shots[1]["img"], looks) == \
        "(Vietnamese woman, 28, grey hoodie) facing (translucent cyan holographic panel) in a dark room."
    srt = video_gen._extract_srt(SUBS)
    assert srt.count("-->") == 2 and "Mình mơ à?" in srt and "```" not in srt


def test_real_episode_package_parses_if_present():
    """The package the workflow actually produced (on this machine) has 30 shots that all parse."""
    real = Path("D:/Code/Video/series/tap_1/goi_san_xuat.md")
    if not real.exists():
        pytest.skip("no local episode package")
    style, shots = video_gen._parse_package(real.read_text(encoding="utf-8"))
    assert style and len(shots) == 30 and all(s["img"] and s["vid"] for s in shots)


@pytest.mark.parametrize("seconds,expected", [(3, 4), (5, 6), (6, 6), (7.5, 8), (12, 8)])
def test_veo_duration_covers_the_shot(seconds, expected):
    assert video_gen._veo_seconds(seconds) == expected


@pytest.mark.parametrize("exc,fatal", [
    (SimpleNamespace(code=403, status="PERMISSION_DENIED"), True),
    (SimpleNamespace(code=429, status="RESOURCE_EXHAUSTED"), False),  # a rate limit is retried first (see _call)
    (Exception("404 model not found for this shot"), False),
    (Exception("400 FAILED_PRECONDITION: billing account required"), True),
    (Exception("400 INVALID_ARGUMENT: prompt was blocked by safety filters"), False),
])
def test_error_classification(exc, fatal):
    assert video_gen._is_fatal(exc) is fatal


def test_no_google_sign_in_keeps_the_script_package(tmp_path, monkeypatch):
    def no_client():
        raise video_gen.StopRendering("đăng nhập Google Gemini không dùng được: sign-in expired")

    monkeypatch.setattr(video_gen, "_gemini_client", no_client)
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=_project(tmp_path))
    assert result["status"] == "not_rendered" and "sign-in expired" in result["reason"]
    assert "vẫn giữ nguyên" in result["note"]
    assert (tmp_path / "series/tap_1/goi_san_xuat.md").read_text(encoding="utf-8") == PACKAGE


class FakeClient:
    """Veo/Imagen stand-in: 'renders' a real short clip with ffmpeg; can be told to refuse (no paid plan)."""

    def __init__(self, ffmpeg, refuse=None, with_audio=True):
        self.calls = []
        client = self

        class Models:
            def list(self):
                return [SimpleNamespace(name="models/veo-3.1-generate-preview"),
                        SimpleNamespace(name="models/veo-3.1-fast-generate-preview"),
                        SimpleNamespace(name="models/imagen-4.0-generate-001"),
                        SimpleNamespace(name="models/gemini-3-flash")]

            def generate_images(self, model, prompt, config):
                client.calls.append(("image", model, prompt))
                return SimpleNamespace(generated_images=[SimpleNamespace(
                    image=SimpleNamespace(image_bytes=b"\x89PNG fake", mime_type="image/png"))])

            def generate_videos(self, model, prompt, image, config):
                client.calls.append(("video", model, prompt, config.duration_seconds, config.aspect_ratio))
                if refuse:
                    raise refuse
                out = Path(client.tmp) / f"veo_{len(client.calls)}.mp4"
                cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                       f"testsrc=size=180x320:rate=24:duration={config.duration_seconds}"]
                if with_audio:
                    cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={config.duration_seconds}"]
                cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
                subprocess.run(cmd, check=True)
                video = SimpleNamespace(video_bytes=out.read_bytes(), uri=None)
                return SimpleNamespace(name=f"operations/{len(client.calls)}", done=True, error=None,
                                       response=SimpleNamespace(generated_videos=[SimpleNamespace(video=video)]))

        self.models = Models()
        self.operations = SimpleNamespace(get=lambda op: op)
        self.files = SimpleNamespace(download=lambda file: b"")


@pytest.fixture
def ffmpeg():
    path = video_gen._ffmpeg()
    if not path:
        pytest.skip("ffmpeg not available")
    return path


def _duration(ffmpeg, path):
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    hh, mm, ss = probe.stderr.split("Duration: ")[1].split(",")[0].split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss), probe.stderr


def test_full_render_trims_joins_and_adds_subtitles(tmp_path, monkeypatch, ffmpeg):
    fake = FakeClient(ffmpeg)
    fake.tmp = tmp_path
    monkeypatch.setattr(video_gen, "_gemini_client", lambda: fake)
    context = _project(tmp_path)
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)

    assert result["status"] == "rendered", result
    assert result["model"]["veo"] == "veo-3.1-generate-preview"  # newest, not the fast variant
    assert result["shots_rendered_now"] == 3 and result["seconds_of_video_paid"] == 6 + 6 + 4
    videos = [c for c in fake.calls if c[0] == "video"]
    assert sorted(c[3] for c in videos) == [4, 6, 6] and all(c[4] == "9:16" for c in videos)
    assert any("(Vietnamese woman, 28, grey hoodie)" in c[2] for c in videos)  # tags expanded for Veo
    final = tmp_path / result["video"]
    seconds, info = _duration(ffmpeg, final)
    assert abs(seconds - 14) < 0.5, seconds  # 5 + 6 + 3: clips trimmed back to the planned shot lengths
    assert "Subtitle" in info and result["subtitles"] is True

    # A second run pays for nothing: every clip is kept.
    fake.calls.clear()
    again = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    assert again["shots_kept_from_before"] == 3 and again["seconds_of_video_paid"] == 0
    assert not [c for c in fake.calls if c[0] == "video"]


def test_clips_without_audio_still_join(tmp_path, monkeypatch, ffmpeg):
    fake = FakeClient(ffmpeg, with_audio=False)
    fake.tmp = tmp_path
    monkeypatch.setattr(video_gen, "_gemini_client", lambda: fake)
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, max_shots=2, use_first_frame=False,
                                            _context=_project(tmp_path))
    assert result["status"] == "rendered" and result["shots_total"] == 2
    assert not [c for c in fake.calls if c[0] == "image"]


def test_no_paid_plan_stops_at_once_and_keeps_package(tmp_path, monkeypatch, ffmpeg):
    refusal = Exception("400 FAILED_PRECONDITION: Veo requires a paid billing account")
    fake = FakeClient(ffmpeg, refuse=refusal)
    fake.tmp = tmp_path
    monkeypatch.setattr(video_gen, "_gemini_client", lambda: fake)
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=_project(tmp_path))
    assert result["status"] == "not_rendered" and "billing" in result["reason"]
    assert len([c for c in fake.calls if c[0] == "video"]) <= video_gen.PARALLEL_SHOTS
    assert not list((tmp_path / "series/tap_1").glob("*.mp4"))


def test_episode_dir_cannot_escape_the_project(tmp_path):
    with pytest.raises(ValueError):
        video_gen.render_episode_video("../outside", _context=_project(tmp_path))


def test_client_is_built_from_the_google_sign_in(monkeypatch):
    """The real client path (not faked): Bearer token from the Gemini connection, no API key header."""
    from types import SimpleNamespace as NS
    import google.genai as genai
    from agentdev.connections import resolver, store

    monkeypatch.setattr(store, "get_store", lambda: NS(list=lambda: [NS(id="g", vendor="gemini")]))
    monkeypatch.setattr(resolver, "resolve_connection",
                        lambda _id: NS(token="oauth-bearer:tok123", base_url="", vendor="gemini"))
    client = video_gen._gemini_client()
    assert isinstance(client, genai.Client)
    headers = client._api_client._http_options.headers
    assert headers.get("Authorization") == "Bearer tok123" and "x-goog-api-key" not in headers

    monkeypatch.setattr(store, "get_store", lambda: NS(list=lambda: []))
    with pytest.raises(video_gen.StopRendering):
        video_gen._gemini_client()
