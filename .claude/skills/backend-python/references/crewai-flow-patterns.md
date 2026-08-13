# CrewAI Flow Patterns

## Flow Structure

```python
from crewai.flow.flow import Flow, listen, start, router

class QueryFlow(Flow[QueryFlowState]):

    @start()
    async def first_phase(self):
        # Entry point — always runs first
        self.state["field"] = value
        self._emit_event(StreamEventType.THINKING, ...)

    @router(first_phase)
    async def route_decision(self):
        if condition:
            return "path_a"
        return "path_b"

    @listen("path_a")
    async def phase_a(self):
        # Runs when router returns "path_a"
        pass

    @listen("path_b")
    async def phase_b(self):
        pass

    @listen(phase_a, phase_b)  # Runs after either
    async def final_phase(self):
        pass
```

## State Management

```python
class QueryFlowState(TypedDict):
    query: str
    conversation_history: list[dict]
    structured_query: dict
    retrieved_documents: list[dict]
    reranked_documents: list[dict]
    final_response: str
    citations: list[dict]
    config: dict  # Dynamic config from MongoDB
    requires_retrieval: bool
    user_filters: dict
```

## Event Emission (SSE)

```python
def _emit_event(self, event_type, status, message, metadata=None):
    self.state["event_type"] = event_type.value
    self.state["event_status"] = status.value
    self.state["event_message"] = message
    self.state["event_metadata"] = metadata or {}
    self.state["event_timestamp"] = datetime.now(timezone.utc).isoformat()
    if self._state_callback:
        self._state_callback(dict(self.state))
```

## LLM Calls in Flow

```python
async def _call_llm(self, prompt: str) -> str:
    response = await asyncio.to_thread(
        litellm.completion,
        model=self.state["config"].get("bedrock_model_id"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=4096,
    )
    return response.choices[0].message.content
```

## Multi-Source Search

```python
async def _multi_source_search(self):
    tasks = []
    for source_type in ["manuale", "ticket", "mail"]:
        filters = {**user_filters, "source_type": source_type}
        if source_type == "mail":
            filters = {"source_type": "mail"}  # No user filters for mail
        tasks.append(self._search_source_type(filters, quota))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [doc for result in results if not isinstance(result, Exception) for doc in result]
```
