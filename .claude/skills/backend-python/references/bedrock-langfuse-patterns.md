# AWS Bedrock & LangFuse Patterns

## LLM Calls via litellm
```python
import litellm

response = await asyncio.to_thread(
    litellm.completion,
    model="eu.anthropic.claude-sonnet-4-5-20250929-v1:0",  # From settings
    messages=[{"role": "user", "content": prompt}],
    temperature=0.0,
    max_tokens=4096,
)
text = response.choices[0].message.content
```

## Embedding Generation

```python
# Bedrock Cohere Embed Multilingual v3
# Input: text string → Output: 256-dim vector (truncated from 1024)

body = json.dumps({
    "texts": [text],
    "input_type": "search_query",  # or "search_document" for ingestion
})
response = bedrock_client.invoke_model(
    modelId="cohere.embed-multilingual-v3",
    body=body,
)
embedding_1024 = response["embeddings"][0]
embedding_256 = embedding_1024[:256]  # Truncate
# L2 normalize
norm = sum(x**2 for x in embedding_256) ** 0.5
embedding_256 = [x / norm for x in embedding_256]
```

**Critical:**
- Use `input_type="search_query"` for queries, `"search_document"` for documents
- Do NOT use `return_response=True` (parameter conflict with Bedrock)
- Auto-batch at 96 texts/request (Bedrock limit)
- Max 4 concurrent batches

## LangFuse Observability

```python
from langfuse.decorators import observe

class ChatService:
    @observe(name="process_query", capture_input=True, capture_output=True)
    async def process_query(self, ...):
        pass
```

## LangFuse Prompt Management

```python
class PromptService:
    def __init__(self, settings):
        self._langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        self._cache = {}  # 5-min TTL

    def get_prompt(self, name: str, **kwargs) -> str:
        prompt = self._langfuse.get_prompt(name)
        return prompt.compile(**kwargs)
        # Fallback to local fallback_prompts.py if LangFuse unavailable
```
