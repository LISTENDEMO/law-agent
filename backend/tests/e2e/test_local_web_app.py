from __future__ import annotations

import os
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import expect, sync_playwright


APP_URL = os.environ.get("LAWAGENT_E2E_URL", "http://127.0.0.1:3003")


def test_local_web_app_supports_chat_evidence_and_trace_flow() -> None:
    if not _is_running(APP_URL):
        pytest.skip(f"local web app is not running at {APP_URL}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 850})
        page.goto(APP_URL)
        page.wait_for_load_state("networkidle")

        page.wait_for_function("window.__lawagentReactReady === true", timeout=10_000)

        page.locator('[data-lawagent-prompt="民法典关于保证责任有哪些规定？"]').click()
        expect(page.locator("[data-lawagent-query]")).to_have_value("民法典关于保证责任有哪些规定？")
        unique_query = f"民法典关于保证责任有哪些规定？ E2E-{time.time_ns()}"
        page.locator("[data-lawagent-query]").fill(unique_query)
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/chat/stream"), timeout=10_000
        ) as response_info:
            page.locator("[data-lawagent-submit]").click()
        expect(page.locator("[data-lawagent-query]")).to_have_value("")
        response = response_info.value
        assert response.status == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        page.wait_for_function(
            """() => {
                const bubble = document.querySelector('.chat-bubble.assistant .bubble-content');
                return Boolean(
                    bubble &&
                    bubble.querySelector('.typing-cursor') &&
                    (bubble.textContent || '').trim().length > 0
                );
            }""",
            timeout=90_000,
        )

        expect(page.locator("[data-lawagent-message-thread]")).to_contain_text("LawAgent", timeout=90_000)
        expect(page.locator("[data-lawagent-structured-answer]")).to_contain_text(
            "核心结论", timeout=90_000
        )
        expect(page.locator("[data-lawagent-structured-answer]")).to_contain_text("关键要点")
        expect(page.locator("[data-lawagent-structured-answer]")).to_contain_text("适用提示")
        first_evidence = page.locator("[data-lawagent-evidence-card]").first
        expect(first_evidence).to_be_visible(timeout=90_000)
        first_evidence.click()
        assert "active" in (first_evidence.get_attribute("class") or "")
        page.set_viewport_size({"width": 720, "height": 850})
        page.get_by_role("tab", name="轨迹").click()
        expect(page.locator("[data-lawagent-event-log]")).to_contain_text("EVENTS")

        page.set_viewport_size({"width": 1366, "height": 850})
        page.reload()
        page.wait_for_function("window.__lawagentReactReady === true", timeout=10_000)
        persisted_session = page.locator(".history-item").filter(has_text=unique_query).first
        expect(persisted_session).to_be_visible(timeout=10_000)
        persisted_session.click()
        expect(page.locator("[data-lawagent-message-thread]")).to_contain_text(unique_query)
        expect(page.locator("[data-lawagent-structured-answer]")).to_contain_text("核心结论")
        session_id = persisted_session.get_attribute("data-lawagent-session-id")
        assert session_id
        cleanup_request = urllib.request.Request(
            f"{APP_URL}/api/v1/sessions/{session_id}", method="DELETE"
        )
        with urllib.request.urlopen(cleanup_request, timeout=5) as cleanup_response:
            assert cleanup_response.status == 204
        browser.close()


def _is_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status < 500
    except (urllib.error.URLError, TimeoutError):
        return False
