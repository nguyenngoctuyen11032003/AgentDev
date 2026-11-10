"""Per-shot prompts for Google Flow: the same prompts Veo would get, made from the production package by code."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import video as route
from agentdev.utils import video_package
from tests.test_video_gen import BIBLE, PACKAGE


def test_flow_prompts_match_the_veo_prompts():
    result = video_package.flow_prompts(PACKAGE, BIBLE)
    assert result["style"].startswith("photorealistic")
    assert [s["number"] for s in result["shots"]] == [1, 2, 3]
    second = result["shots"][1]
    assert second["seconds"] == 6
    # tags expanded (Flow knows nothing about our tags), style first, motion last
    assert second["prompt"] == ("photorealistic, cinematic, 9:16 vertical.. (Vietnamese woman, 28, grey hoodie) facing "
                                "(translucent cyan holographic panel) in a dark room. Motion: Slow push-in.")
    assert second["image_prompt"].endswith("in a dark room.") and "Motion:" not in second["image_prompt"]
    assert result["missing_tags"] == []


def test_flow_prompts_report_tags_without_a_bible():
    result = video_package.flow_prompts(PACKAGE, "")
    assert "[LINH-v1]" in result["shots"][0]["prompt"]
    assert result["missing_tags"] == ["HETHONG-v1", "LINH-v1"]


def test_flow_prompts_of_text_without_shot_lines_is_empty():
    assert video_package.flow_prompts("# Kịch bản\nKhông có shot.", "")["shots"] == []


def _client():
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


def test_route_returns_the_prompts():
    response = _client().post("/api/video/flow-prompts", json={"package": PACKAGE, "bible": BIBLE})
    assert response.status_code == 200
    assert len(response.json()["shots"]) == 3


def test_route_refuses_huge_text():
    response = _client().post("/api/video/flow-prompts", json={"package": "x" * 2_000_001})
    assert response.status_code == 422


def test_route_refuses_other_origins():
    response = _client().post("/api/video/flow-prompts", json={"package": PACKAGE},
                              headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
