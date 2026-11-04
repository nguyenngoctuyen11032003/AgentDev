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
    (clips / "shot_01.key").write_text(video_gen._shot_key(f"{style}. {img} Motion: {vid}", "9:16"),
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
    assert not (episode / ".agentdev_ghep_tmp").exists()


def test_earlier_complete_video_is_kept_as_a_backup(tmp_path, monkeypatch, ffmpeg):
    _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    first = (tmp_path / "series/tap_1/tap_1.mp4").read_bytes()
    video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    backups = sorted((tmp_path / "series/tap_1").glob("tap_1.truoc-*.mp4"))
    assert len(backups) == 2 and backups[0].read_bytes() == first  # every earlier version kept


def test_video_uses_the_connected_google_account(monkeypatch):
    signed_in = SimpleNamespace(models=SimpleNamespace(list=lambda: [SimpleNamespace(name="models/veo-3.0-generate-001")]))
    monkeypatch.setattr(video_gen, "_gemini_client", lambda: signed_in)
    client, models, account = video_gen._connect(use_first_frame=False)
    assert client is signed_in and models["veo"] == "veo-3.0-generate-001" and "Google" in account


def test_account_without_veo_explains_upgrade_and_sign_in_again(monkeypatch):
    no_veo = SimpleNamespace(models=SimpleNamespace(list=lambda: [SimpleNamespace(name="models/gemini-3-flash")]))
    monkeypatch.setattr(video_gen, "_gemini_client", lambda: no_veo)
    with pytest.raises(video_gen.StopRendering) as info:
        video_gen._connect(use_first_frame=True)
    text = str(info.value)
    assert "Đăng nhập lại" in text and "trang Kết nối" in text and "API key" not in text


def test_no_api_key_path_exists(monkeypatch):
    """Only the Connections page sign-in is used: an API key in the environment changes nothing."""
    monkeypatch.setenv("GEMINI_API_KEY", "key-abc")
    assert not hasattr(video_gen, "_key_client") and not hasattr(video_gen, "MEDIA_KEY_ENV")



def test_imagen_becoming_unavailable_does_not_pay_again(tmp_path, monkeypatch, ffmpeg):
    """Clips made with a first frame stay valid when the next run has no Imagen (or use_first_frame=False)."""
    fake = _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    video_gen.render_episode_video("series/tap_1", confirmed=True, use_first_frame=True, _context=context)
    fake.calls.clear()
    estimate = video_gen.render_episode_video("series/tap_1", use_first_frame=False, _context=context)
    assert estimate["shots_to_render"] == 0 and estimate["seconds_of_video_to_pay"] == 0
    again = video_gen.render_episode_video("series/tap_1", confirmed=True, use_first_frame=False, _context=context)
    assert again["shots_kept_from_before"] == 3 and not _paid(fake)


def test_estimate_counts_a_changed_prompt_as_to_pay(tmp_path, monkeypatch, ffmpeg):
    _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    package = tmp_path / "series/tap_1/goi_san_xuat.md"
    package.write_text(package.read_text(encoding="utf-8").replace("Handheld jolt", "Slow tilt"), encoding="utf-8")
    estimate = video_gen.render_episode_video("series/tap_1", _context=context)
    assert estimate["shots_to_render"] == 1


def test_second_concurrent_render_of_the_same_episode_is_refused(tmp_path, monkeypatch, ffmpeg):
    fake = _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    clips = tmp_path / "series/tap_1/video"
    clips.mkdir()
    (clips / ".render.lock").write_text("123", encoding="utf-8")
    result = video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    assert result["status"] == "not_rendered" and "lượt chạy khác" in result["reason"] and not _paid(fake)


def test_user_folder_named_like_the_old_temp_folder_is_left_alone(tmp_path, monkeypatch, ffmpeg):
    _fake(tmp_path, ffmpeg, monkeypatch)
    context = _project(tmp_path)
    mine = tmp_path / "series/tap_1/_ghep"
    mine.mkdir()
    (mine / "notes.txt").write_text("của tôi", encoding="utf-8")
    video_gen.render_episode_video("series/tap_1", confirmed=True, _context=context)
    assert (mine / "notes.txt").read_text(encoding="utf-8") == "của tôi"
    assert not (tmp_path / "series/tap_1/video/.render.lock").exists()
