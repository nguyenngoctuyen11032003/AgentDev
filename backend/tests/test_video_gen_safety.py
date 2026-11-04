"""render_episode_video: money safety, resumption, cancellation (from the adversarial review of the tool)."""

import subprocess
from types import SimpleNamespace

import pytest

from functions.function_calling import video_gen
from tests.test_video_gen import BIBLE, PACKAGE, SUBS, FakeClient, _duration, _project, ffmpeg  # noqa: F401


def _fake(tmp_path, ffmpeg_path, monkeypatch, **kwargs):
    fake = FakeClient(ffmpeg_path, **kwargs)
    fake.tmp = tmp_path
    monkeypatch.setattr(video_gen, "_gemini_client", lambda: fake)
    return fake


def _paid(fake):
    return [c for c in fake.calls if c[0] == "video"]


def test_without_confirmation_nothing_is_spent(tmp_path, monkeypatch, ffmpeg):
    fake = _fake(tmp_path, ffmpeg, monkeypatch)
    result = video_gen.render_episode_video("series/tap_1", _context=_project(tmp_path))
    assert result["status"] == "needs_confirmation" and result["shots_to_render"] == 3
    assert result["seconds_of_video_to_pay"] == 4 + 6 + 6 and fake.calls == []
    assert not (tmp_path / "series/tap_1/video").exists()


def test_bad_aspect_ratio_is_refused_before_any_call(tmp_path):
    with pytest.raises(ValueError):
        video_gen.render_episode_video("series/tap_1", confirmed=True, aspect_ratio="4:3", _context=_project(tmp_path))


def test_cut_off_clip_is_rendered_again_not_kept(tmp_path, monkeypatch, ffmpeg):
    _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    clips = tmp_path / "series/tap_1/video"
    clips.mkdir()
    (clips / "shot_01.mp4").write_bytes(b"\x00\x00")  # an interrupted write
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    assert result["shots_kept_from_before"] == 0 and result["shots_rendered_now"] == 3


def test_changed_ratio_rerenders_instead_of_mixing_clips(tmp_path, monkeypatch, ffmpeg):
    fake = _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    video_gen.render_episode_video("series/tap_1", confirmed=True, aspect_ratio="9:16", _context=context)
    fake.calls.clear()
    again = video_gen.render_episode_video("series/tap_1", confirmed=True, aspect_ratio="16:9", _context=context)
    assert again["shots_rendered_now"] == 3 and len(_paid(fake)) == 3


def test_started_operation_is_resumed_not_paid_again(tmp_path, monkeypatch, ffmpeg):
    """Shot 1 was started by an earlier call that never downloaded it: its saved operation id is resumed."""
    fake = _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    clips = tmp_path / "series/tap_1/video"
    clips.mkdir()
    style, shots = video_gen._parse_package(PACKAGE)
    looks = video_gen._parse_bible(BIBLE)
    img, vid = (video_gen._expand_tags(shots[0][k], looks) for k in ("img", "vid"))
    (clips / "shot_01.key").write_text(video_gen._shot_key(f"{style}. {img} Motion: {vid}", "9:16", True),
                                       encoding="utf-8")
    (clips / "shot_01.op").write_text("operations/earlier", encoding="utf-8")

    earlier = tmp_path / "earlier.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=180x320:rate=24:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(earlier)], check=True)
    resumed = []

    def get(operation):
        resumed.append(getattr(operation, "name", None))
        video = SimpleNamespace(video_bytes=earlier.read_bytes(), uri=None)
        return SimpleNamespace(name="operations/earlier", done=True, error=None,
                               response=SimpleNamespace(generated_videos=[SimpleNamespace(video=video)]))

    fake.operations = SimpleNamespace(get=get)
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    assert "operations/earlier" in resumed
    assert len(_paid(fake)) == 2, "only shots 2 and 3 are started anew"
    assert result["status"] == "rendered" and not (clips / "shot_01.op").exists()


def test_cancel_reaches_the_pool_workers_and_stops_new_shots(tmp_path, monkeypatch, ffmpeg):
    fake = _fake(tmp_path, ffmpeg, monkeypatch)
    monkeypatch.setattr(video_gen, "_current_cancel_event", lambda: SimpleNamespace(is_set=lambda: True))
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=_project(tmp_path))
    assert not _paid(fake), "a stopped run must not start paid renders"
    assert result["status"] == "not_rendered"


class _RateLimit(Exception):
    code = 429

    def __init__(self):
        super().__init__("429 RESOURCE_EXHAUSTED: per-minute quota")


def test_rate_limit_is_retried_then_succeeds(tmp_path, monkeypatch, ffmpeg):
    monkeypatch.setattr(video_gen, "RETRY_SECONDS", (0, 0))
    fake = _fake(tmp_path, ffmpeg, monkeypatch)
    real, state = fake.models.generate_videos, {"n": 0}

    def flaky(model, prompt, image, config):
        state["n"] += 1
        if state["n"] == 1:
            raise _RateLimit()
        return real(model=model, prompt=prompt, image=image, config=config)

    fake.models.generate_videos = flaky
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, max_shots=1, use_first_frame=False,
                                            _context=_project(tmp_path))
    assert result["status"] == "rendered" and state["n"] == 2


def test_rate_limit_that_never_clears_stops_the_run(tmp_path, monkeypatch, ffmpeg):
    monkeypatch.setattr(video_gen, "RETRY_SECONDS", (0,))
    fake = _fake(tmp_path, ffmpeg, monkeypatch)

    def always(model, prompt, image, config):
        raise _RateLimit()

    fake.models.generate_videos = always
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=_project(tmp_path))
    assert result["status"] == "not_rendered" and "hạn mức" in result["reason"]


def test_quote_in_folder_name_and_long_shot_keep_video_and_subtitles_aligned(tmp_path, monkeypatch, ffmpeg):
    """An apostrophe in the episode folder broke the join; a 10 s shot (Veo gives at most 8 s) shifted every later
    subtitle. The clip is held on its last frame, so the video keeps its planned 5 + 10 + 3 = 18 s."""
    package = PACKAGE.replace("| 2 | 5-11 | 6 | MS |", "| 2 | 5-15 | 10 | MS |")
    package = package.replace("| 3 | 11-14 | 3 | CU |", "| 3 | 15-18 | 3 | CU |")
    episode = tmp_path / "series" / "Tap O'Neil"
    episode.mkdir(parents=True)
    (episode / "goi_san_xuat.md").write_text(package, encoding="utf-8")
    (episode / "loi_thoai_phu_de.md").write_text(SUBS, encoding="utf-8")
    (tmp_path / "series" / "ho_so_nhan_vat.md").write_text(BIBLE, encoding="utf-8")
    _fake(tmp_path, ffmpeg, monkeypatch)
    result = video_gen.render_episode_video("series/Tap O'Neil", confirmed=True,
                                            _context={"python_workspace_root": str(tmp_path)})
    assert result["status"] == "rendered", result
    seconds, _ = _duration(ffmpeg, tmp_path / result["video"])
    assert abs(seconds - 18) < 0.6, seconds
    assert not (episode / "_ghep").exists()


def test_earlier_complete_video_is_kept_as_a_backup(tmp_path, monkeypatch, ffmpeg):
    _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    first = (tmp_path / "series/tap_1/tap_1.mp4").read_bytes()
    video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    assert (tmp_path / "series/tap_1/tap_1.truoc.mp4").read_bytes() == first


def test_paid_api_key_is_used_for_media_before_the_sign_in(monkeypatch):
    import google.genai as genai

    monkeypatch.setenv("GEMINI_API_KEY", "key-abc")
    client = video_gen._gemini_client()
    assert isinstance(client, genai.Client) and client._api_client.api_key == "key-abc"


def test_no_key_and_no_sign_in_explains_how_to_enable_video(monkeypatch):
    from agentdev.connections import store

    for name in video_gen.MEDIA_KEY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(store, "get_store", lambda: SimpleNamespace(list=lambda: []))
    with pytest.raises(video_gen.StopRendering) as info:
        video_gen._gemini_client()
    assert "GEMINI_API_KEY" in str(info.value) and "AI Studio" in str(info.value)
