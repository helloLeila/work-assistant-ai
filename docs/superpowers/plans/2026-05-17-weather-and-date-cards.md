# Weather And Date Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured weather and date cards to the chat experience, persist them through history, and make the feature easy to debug from VSCode and short project commands.

**Architecture:** Keep the current token-stream chat flow, but add a parallel structured `artifact` payload for `weather_card` and `date_card`. The backend owns artifact creation, SSE transports the artifact events, history stores them, and Vue renders dedicated cards without parsing assistant prose.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, Pydantic, SSE, Vue 3, TypeScript, Vite, pytest, Vitest, `@vue/test-utils`, VSCode workspace config.

---

## Commit Budget

The feature already has 4 documentation commits in git. This plan covers the 10 remaining implementation commits:

1. shared backend artifact models
2. SSE artifact event plumbing
3. history persistence and replay
4. local time and date card generation
5. weather extractor expansion
6. weather card assembly in the backend node
7. frontend artifact test harness and typing
8. date card UI and chat bubble integration
9. weather card UI and workspace integration
10. VSCode config, short commands, and final regression sweep

## File Map

- Create: `backend/app/models/artifacts.py`
- Modify: `backend/app/models/domain.py`
- Modify: `backend/app/models/chat.py`
- Modify: `backend/app/core/streaming.py`
- Modify: `backend/app/agents/office_assistant_graph.py`
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/app/services/history_service.py`
- Create: `backend/app/services/time_service.py`
- Modify: `backend/app/nodes/generate_node.py`
- Modify: `backend/app/services/weather_extractor.py`
- Modify: `backend/app/nodes/web_search_node.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/composables/useChatStream.ts`
- Modify: `frontend/src/pages/WorkspacePage.vue`
- Modify: `frontend/src/components/ChatMessageBubble.vue`
- Create: `frontend/src/components/DateArtifactCard.vue`
- Create: `frontend/src/components/WeatherArtifactCard.vue`
- Create: `frontend/tests/useChatStream.test.ts`
- Create: `frontend/tests/DateArtifactCard.test.ts`
- Create: `frontend/tests/WeatherArtifactCard.test.ts`
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `.vscode/settings.json`
- Create: `.vscode/launch.json`
- Create: `.vscode/tasks.json`
- Create: `.vscode/.env`
- Modify: `Makefile`
- Create: `backend/tests/test_artifact_models.py`
- Create: `backend/tests/test_history_service.py`
- Modify: `backend/tests/test_generate_node.py`
- Modify: `backend/tests/test_weather_extractor.py`
- Modify: `backend/tests/test_web_search_node.py`
- Modify: `backend/tests/test_chat_stream_api.py`

## Task 1: Shared Artifact Models

**Files:**
- Create: `backend/app/models/artifacts.py`
- Modify: `backend/app/models/domain.py`
- Modify: `backend/app/models/chat.py`
- Test: `backend/tests/test_artifact_models.py`

- [ ] **Step 1: Write the failing test**

```python
from app.models.artifacts import DateArtifact, DateArtifactData, WeatherArtifact, WeatherArtifactData


def test_artifact_models_round_trip():
    weather = WeatherArtifact(
        data=WeatherArtifactData(
            city="深圳",
            relative_day_label="今天",
            forecast_date="2026-05-17",
            weekday_label="星期日",
            summary="多云",
            source_name="天气网",
        )
    )
    date = DateArtifact(
        data=DateArtifactData(
            title="今天",
            date_text="2026年05月17日",
            weekday_label="星期日",
            timezone="Asia/Shanghai",
        )
    )
    assert weather.kind == "weather_card"
    assert date.kind == "date_card"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-backend`
Expected: import error for `app.models.artifacts`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/models/artifacts.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WeatherForecastItem(BaseModel):
    date: str
    weekday_label: str
    relative_day_label: str
    condition: str
    temp_low_c: int | None = None
    temp_high_c: int | None = None


class ArtifactCompleteness(BaseModel):
    has_current: bool = False
    has_forecast: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class WeatherArtifactData(BaseModel):
    city: str
    relative_day_label: str
    forecast_date: str
    weekday_label: str
    summary: str
    current_temp_c: int | None = None
    temp_low_c: int | None = None
    temp_high_c: int | None = None
    feels_like_c: int | None = None
    wind_text: str = ""
    air_quality: str = ""
    humidity: str = ""
    precipitation: str = ""
    uv_index: str = ""
    source_name: str
    source_url: str = ""
    forecast_items: list[WeatherForecastItem] = Field(default_factory=list)
    completeness: ArtifactCompleteness = Field(default_factory=ArtifactCompleteness)


class DateArtifactData(BaseModel):
    title: str
    date_text: str
    weekday_label: str
    timezone: str


class WeatherArtifact(BaseModel):
    kind: Literal["weather_card"] = "weather_card"
    version: int = 1
    data: WeatherArtifactData


class DateArtifact(BaseModel):
    kind: Literal["date_card"] = "date_card"
    version: int = 1
    data: DateArtifactData
```

Update `ChatTurn` and history-facing models with `artifacts: list[dict[str, object]] = Field(default_factory=list)`.

Add comments explaining that artifact schemas are shared between SSE, history, and Vue props.

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-backend`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/artifacts.py backend/app/models/domain.py backend/app/models/chat.py backend/tests/test_artifact_models.py
git commit -m "feat: add shared artifact models"
```

## Task 2: SSE Artifact Event Plumbing

**Files:**
- Modify: `backend/app/core/streaming.py`
- Modify: `backend/app/agents/office_assistant_graph.py`
- Modify: `backend/app/services/chat_service.py`
- Test: `backend/tests/test_chat_stream_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_chat_stream_emits_artifact_event(monkeypatch):
    import app.nodes.generate_node as generate_module
    import app.nodes.web_search_node as web_search_module
    from app.main import create_app
    from app.models.domain import WebSearchHit, WebSearchResult
    from fastapi.testclient import TestClient

    class FakeIPLocationService:
        async def lookup(self, ip: str) -> str | None:
            return "深圳"

    class FakeWebSearchService:
        async def search(
            self,
            query: str,
            *,
            max_results: int | None = None,
            freshness: str | None = None,
        ) -> WebSearchResult:
            return WebSearchResult(
                query=query,
                results=[
                    WebSearchHit(
                        title="深圳天气预报",
                        url="https://weather.example.com/shenzhen",
                        snippet="2026年05月17日深圳天气预报：多云，温度:26/20°C，南风3级，空气质量优。",
                        site_name="天气网",
                    )
                ],
            )

    async def fail_if_llm_is_used(**kwargs):
        raise AssertionError("weather direct answer should not call stream_final_answer")

    monkeypatch.setenv("BOCHA_API_KEY", "dummy-key")
    monkeypatch.setattr(web_search_module, "get_ip_location_service", lambda: FakeIPLocationService())
    monkeypatch.setattr(web_search_module, "get_web_search_service", lambda: FakeWebSearchService())
    monkeypatch.setattr(generate_module, "stream_final_answer", fail_if_llm_is_used)

    client = TestClient(create_app())
    token_response = client.post("/api/auth/login", json={"username": "li.wei", "password": "RuiRui123!"})
    token = token_response.json()["access_token"]

    with client.stream(
        "GET",
        "/api/chat/stream",
        headers={"X-Forwarded-For": "8.8.8.8"},
        params={"session_id": "artifact-test", "query": "天气", "access_token": token},
    ) as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert 'data: {"type":"artifact"' in body
    assert "weather_card" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-chat-stream`
Expected: `artifact` event is missing.

- [ ] **Step 3: Write minimal implementation**

Add to `SSEStreamer`:

```python
async def push_artifact(self, artifact: dict[str, Any]) -> None:
    await self._queue.put(StreamEvent(type="artifact", payload={"artifact": artifact}))
```

Thread `artifacts` through `GraphState`. In `ChatService.run_streaming_chat()`, collect `state.get("artifacts", [])` and call `await streamer.push_artifact(...)` for each artifact before `push_done()`.

Add comments that artifact events are parallel to token events and are not a replacement.

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-chat-stream`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/streaming.py backend/app/agents/office_assistant_graph.py backend/app/services/chat_service.py backend/tests/test_chat_stream_api.py
git commit -m "feat: stream structured artifacts"
```

## Task 3: History Persistence And Replay

**Files:**
- Modify: `backend/app/services/history_service.py`
- Modify: `backend/app/models/domain.py`
- Test: `backend/tests/test_history_service.py`

- [ ] **Step 1: Write the failing test**

```python
from types import SimpleNamespace

from app.services.history_service import HistoryService


def test_append_turn_persists_artifacts(tmp_path, monkeypatch):
    history_path = tmp_path / "chat_history.json"
    history_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("app.services.history_service.get_settings", lambda: SimpleNamespace(chat_history_path=history_path))
    service = HistoryService()
    service.append_turn(
        user_id="u1",
        session_id="s1",
        title="深圳天气",
        role="assistant",
        content="深圳今天多云。",
        sources=[],
        artifacts=[{"kind": "weather_card", "version": 1, "data": {"city": "深圳"}}],
    )
    sessions, _ = service.list_sessions("u1")
    assert sessions[0].turns[0].artifacts[0]["kind"] == "weather_card"


def test_history_loads_legacy_turns_without_artifacts(tmp_path, monkeypatch):
    history_path = tmp_path / "chat_history.json"
    history_path.write_text(
        '{"u1":{"s1":{"session_id":"s1","title":"old","updated_at":"2026-05-17T00:00:00","turns":[{"role":"assistant","content":"old","created_at":"2026-05-17 00:00:00","sources":[]}]}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("app.services.history_service.get_settings", lambda: SimpleNamespace(chat_history_path=history_path))
    service = HistoryService()
    sessions, _ = service.list_sessions("u1")
    assert sessions[0].turns[0].artifacts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-history`
Expected: `artifacts` field missing or validation error.

- [ ] **Step 3: Write minimal implementation**

Update `HistoryService.append_turn()` to accept `artifacts: list[dict[str, object]] | None = None` and persist the list into the stored assistant turn JSON.

Keep the Pydantic turn model backward compatible by defaulting `artifacts` to `[]`.

Add comments explaining that `content`, `sources`, and `artifacts` are persisted together so refresh/reopen can recover the same assistant message.

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-history`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/history_service.py backend/app/models/domain.py backend/tests/test_history_service.py
git commit -m "feat: persist structured chat artifacts"
```

## Task 4: Local Time And Date Card

**Files:**
- Create: `backend/app/services/time_service.py`
- Modify: `backend/app/nodes/generate_node.py`
- Test: `backend/tests/test_generate_node.py`

- [ ] **Step 1: Write the failing test**

```python
from types import SimpleNamespace
import asyncio

from app.nodes.generate_node import generate_node


def test_current_date_question_emits_date_card():
    class FakeStreamer:
        def __init__(self) -> None:
            self.artifacts: list[dict[str, object]] = []

        async def push_token(self, token: str) -> None:
            return None

        async def push_artifact(self, artifact: dict[str, object]) -> None:
            self.artifacts.append(artifact)

    runtime = SimpleNamespace(context=SimpleNamespace(streamer=FakeStreamer()))
    result = asyncio.run(generate_node({"query": "今天几号", "intent": "chitchat"}, runtime))
    assert "2026年05月17日" in result["final_answer"]
    assert any(item["kind"] == "date_card" for item in result["artifacts"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-generate`
Expected: `date_card` is missing from the node output.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/time_service.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo


def get_local_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))
```

Update `generate_node.py` so the date fast-path returns both the existing text answer and a `date_card` artifact payload using the same local time source.

Add comments explaining why the date text and date card must stay in sync.

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-generate`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/time_service.py backend/app/nodes/generate_node.py backend/tests/test_generate_node.py
git commit -m "feat: add date card fast path"
```

## Task 5: Weather Extractor Expansion

**Files:**
- Modify: `backend/app/services/weather_extractor.py`
- Test: `backend/tests/test_weather_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date

from app.models.domain import WebSearchHit
from app.services.weather_extractor import WeatherExtractor


def test_extract_weather_forecast_items_and_completeness():
    extractor = WeatherExtractor()
    hit = WebSearchHit(
        title="深圳天气预报",
        url="https://weather.example.com/shenzhen",
        snippet="2026年05月17日深圳天气预报：多云，温度:26/20°C，南风3级。2026年05月18日晴，28/22°C。2026年05月19日多云，29/23°C。",
        site_name="天气网",
    )
    report = extractor.extract(
        query="深圳天气",
        search_query="深圳 天气",
        results=[hit],
        today=date(2026, 5, 17),
    )
    assert report is not None
    assert len(report.forecast_items) == 3
    assert report.completeness.has_forecast is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-weather`
Expected: forecast items and completeness are missing.

- [ ] **Step 3: Write minimal implementation**

Extend the extractor to emit a normalized main-day structure plus up to 3 forecast items and a completeness summary.

Keep the strict-date behavior already in place:

- today queries require exact date
- stale snippets stay rejected

Add comments explaining that forecast items are capped at 3 and missing optional fields are acceptable.

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-weather`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/weather_extractor.py backend/tests/test_weather_extractor.py
git commit -m "feat: expand weather normalization"
```

## Task 6: Weather Card Assembly In Backend

**Files:**
- Modify: `backend/app/nodes/web_search_node.py`
- Modify: `backend/app/agents/office_assistant_graph.py`
- Test: `backend/tests/test_web_search_node.py`

- [ ] **Step 1: Write the failing test**

```python
def test_weather_query_emits_weather_card(monkeypatch):
    import asyncio
    import app.nodes.web_search_node as web_search_module
    from app.models.domain import WebSearchHit, WebSearchResult

    class FakeWebSearchService:
        async def search(
            self,
            query: str,
            *,
            max_results: int | None = None,
            freshness: str | None = None,
        ) -> WebSearchResult:
            return WebSearchResult(
                query=query,
                results=[
                    WebSearchHit(
                        title="深圳天气预报",
                        url="https://weather.example.com/shenzhen",
                        snippet="2026年05月17日深圳天气预报：多云，温度:26/20°C，南风3级，空气质量优。",
                        site_name="天气网",
                    )
                ],
            )

    monkeypatch.setenv("BOCHA_API_KEY", "dummy-key")
    monkeypatch.setattr(web_search_module, "get_web_search_service", lambda: FakeWebSearchService())
    result = asyncio.run(web_search_module.web_search_node({"query": "深圳天气"}))
    assert result["structured_data"]["weather_report"]["city"] == "深圳"
    assert result["structured_data"]["weather_report"]["forecast_date"] == "2026-05-17"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-web-search`
Expected: `weather_card` artifact is missing.

- [ ] **Step 3: Write minimal implementation**

Keep the summary text, but also build a `weather_card` artifact from the normalized weather report and store it in graph state so `ChatService` can stream it.

Add comments explaining:

- why the summary text still exists
- why the card is separate
- why `暂无` is allowed for optional fields

- [ ] **Step 4: Run test to verify it passes**

Run: `make test-web-search`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/nodes/web_search_node.py backend/app/agents/office_assistant_graph.py backend/tests/test_web_search_node.py
git commit -m "feat: assemble weather cards in backend"
```

## Task 7: Frontend Artifact Harness And Typing

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/composables/useChatStream.ts`
- Test: `frontend/tests/useChatStream.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { applyStreamPayload } from "../src/composables/useChatStream";
import type { ChatMessage } from "../src/types";

it("stores artifact events on the active assistant message", () => {
  const message = {
    id: "a1",
    role: "assistant",
    content: "",
    createdAt: "2026-05-17 10:00",
    artifacts: [],
  } as ChatMessage;

  applyStreamPayload(message, {
    type: "artifact",
    artifact: {
      kind: "date_card",
      version: 1,
      data: {
        title: "今天",
        dateText: "2026年05月17日",
        weekdayLabel: "星期日",
        timezone: "Asia/Shanghai",
      },
    },
  });

  expect(message.artifacts).toHaveLength(1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test`
Expected: Vitest is not wired up yet.

- [ ] **Step 3: Write minimal implementation**

Add Vitest, jsdom, and `@vue/test-utils` to the frontend dev dependencies and configure a `test` script.

Extend TypeScript types with:

- `MessageArtifact`
- `WeatherArtifactData`
- `DateArtifactData`

Add an exported `applyStreamPayload()` helper in `useChatStream.ts` so `onmessage` and the test can share the same event handling logic.

Add comments where the SSE event is converted into the current assistant message state.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/vitest.config.ts frontend/src/types/index.ts frontend/src/composables/useChatStream.ts frontend/tests/useChatStream.test.ts
git commit -m "feat: add frontend artifact test harness"
```

## Task 8: Date Card UI And Bubble Integration

**Files:**
- Create: `frontend/src/components/DateArtifactCard.vue`
- Modify: `frontend/src/components/ChatMessageBubble.vue`
- Modify: `frontend/src/pages/WorkspacePage.vue`
- Test: `frontend/tests/DateArtifactCard.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { mount } from "@vue/test-utils";
import DateArtifactCard from "../src/components/DateArtifactCard.vue";

it("renders the date card text", () => {
  const wrapper = mount(DateArtifactCard, {
    props: {
      artifact: {
        kind: "date_card",
        version: 1,
        data: {
          title: "今天",
          dateText: "2026年05月17日",
          weekdayLabel: "星期日",
          timezone: "Asia/Shanghai",
        },
      },
    },
  });

  expect(wrapper.text()).toContain("2026年05月17日");
  expect(wrapper.text()).toContain("星期日");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test`
Expected: component does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `DateArtifactCard.vue` and add an artifact rendering branch in `ChatMessageBubble.vue` under the message body and above sources.

Keep the card compact and aligned with the chosen B3 family.

Add comments explaining why the date card is visually redundant but still useful.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DateArtifactCard.vue frontend/src/components/ChatMessageBubble.vue frontend/src/pages/WorkspacePage.vue frontend/tests/DateArtifactCard.test.ts
git commit -m "feat: render date cards in chat"
```

## Task 9: Weather Card UI And Workspace Integration

**Files:**
- Create: `frontend/src/components/WeatherArtifactCard.vue`
- Modify: `frontend/src/components/ChatMessageBubble.vue`
- Modify: `frontend/src/pages/WorkspacePage.vue`
- Test: `frontend/tests/WeatherArtifactCard.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { mount } from "@vue/test-utils";
import WeatherArtifactCard from "../src/components/WeatherArtifactCard.vue";

it("renders the weather card sections", () => {
  const wrapper = mount(WeatherArtifactCard, {
    props: {
      artifact: {
        kind: "weather_card",
        version: 1,
        data: {
          city: "深圳",
          relativeDayLabel: "今天",
          forecastDate: "2026-05-17",
          weekdayLabel: "星期日",
          summary: "多云",
          currentTempC: 26,
          tempLowC: 20,
          tempHighC: 26,
          feelsLikeC: 25,
          windText: "南风3级",
          airQuality: "优",
          humidity: "暂无",
          precipitation: "暂无",
          uvIndex: "暂无",
          sourceName: "天气网",
          sourceUrl: "https://weather.example.com/shenzhen",
          forecastItems: [],
          completeness: { hasCurrent: true, hasForecast: false, missingFields: [] },
        },
      },
    },
  });

  expect(wrapper.text()).toContain("深圳");
  expect(wrapper.text()).toContain("南风3级");
  expect(wrapper.text()).toContain("空气质量优");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test`
Expected: no weather card component yet.

- [ ] **Step 3: Write minimal implementation**

Create `WeatherArtifactCard.vue` using the B3 layout chosen in brainstorming. Render:

- top line with city/date/weekday
- main temperature block
- summary metrics
- forecast sub-cards
- source footer

Add comments around fallback display rules for `暂无`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WeatherArtifactCard.vue frontend/src/components/ChatMessageBubble.vue frontend/src/pages/WorkspacePage.vue frontend/tests/WeatherArtifactCard.test.ts
git commit -m "feat: render weather cards in chat"
```

## Task 10: VSCode Config, Short Commands, And Final Regression Sweep

**Files:**
- Create: `.vscode/settings.json`
- Create: `.vscode/launch.json`
- Create: `.vscode/tasks.json`
- Create: `.vscode/.env`
- Modify: `Makefile`
- Modify: `frontend/package.json`
- Test: `backend/tests/test_chat_stream_api.py`
- Test: `backend/tests/test_history_service.py`
- Test: `frontend/tests/useChatStream.test.ts`
- Test: `frontend/tests/DateArtifactCard.test.ts`
- Test: `frontend/tests/WeatherArtifactCard.test.ts`

- [ ] **Step 1: Write the failing test**

This task is mostly config, so use the operational failure for the first check:

Run: `make test-weather`
Expected: `No rule to make target 'test-weather'`.

- [ ] **Step 2: Run test to verify it fails**

Run: `make test-weather`
Expected: missing target.

- [ ] **Step 3: Write minimal implementation**

Add short commands to the root `Makefile`:

```make
test-weather:
	PYTHONPATH=backend pytest backend/tests/test_weather_extractor.py -q
```

Mirror the same pattern for:

- `test-web-search`
- `test-generate`
- `test-chat-stream`
- `test-history`
- `test-backend`

Add `.vscode` debug config that points VSCode at the project venv and the backend tests, with debug entries for:

- `Debug Backend API`
- `Debug Current Pytest File`
- `Debug Current Test`

Add comments explaining these files are safe to commit because they contain only local debug defaults and no secrets.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
make test-weather
make test-web-search
make test-generate
make test-chat-stream
make test-history
make test-backend
```

Expected: each command runs the intended slice and passes.

- [ ] **Step 5: Commit**

```bash
git add .vscode/settings.json .vscode/launch.json .vscode/tasks.json .vscode/.env Makefile frontend/package.json
git commit -m "feat: add vscode debug workflow and short commands"
```

## Plan Coverage Check

- Weather card and date card data models are covered by Tasks 1, 4, 5, 6, 7, 8, and 9.
- SSE artifact transport is covered by Tasks 2 and 6.
- History persistence and replay are covered by Task 3 and the frontend integration tasks.
- VSCode debug workflow and short commands are covered by Task 10.
- The spec's explicit comment requirement is covered in every task that touches a new file or protocol boundary.
- The required debug playbook is already in the spec; Task 10 makes the project runnable in the way the playbook describes.

## Placeholder Scan

This plan intentionally avoids:

- `TBD`
- `TODO`
- `fill in details`
- `write tests for the above`
- vague references like `handle edge cases`

## Type Consistency Check

- `MessageArtifact` is introduced once in backend and mirrored in frontend types.
- `WeatherArtifactData` and `DateArtifactData` are the only artifact payload types in this plan.
- `artifacts` is the only plural field name used across SSE, history, and frontend state.
- `test-weather`, `test-web-search`, `test-generate`, `test-chat-stream`, `test-history`, and `test-backend` are the only short commands referenced by the plan.
