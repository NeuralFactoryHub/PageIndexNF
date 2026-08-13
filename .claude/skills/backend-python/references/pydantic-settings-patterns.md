# Pydantic Settings Patterns

## Settings Singleton

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    env: str = "dev"
    stage: str = "dev"
    log_level: str = "INFO"

    # Required fields (no default = required)
    weaviate_url: str
    weaviate_api_key: str

    # Optional with defaults
    retrieval_top_k: int = 30
    rerank_top_n: int = 15

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

## Pydantic v2 Model Pattern

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class SourceType(str, Enum):
    MANUALE = "manuale"
    FAQ = "faq"
    MAIL = "mail"
    TICKET = "ticket"

class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    filters: Optional[FilterFields] = None
    top_k: int = Field(default=20, ge=1, le=100)

class ChunkResult(BaseModel):
    chunk_id: str
    content: str
    score: float = Field(ge=0, le=1)
    metadata: dict = Field(default_factory=dict)
```

## MongoDB Document Schema

```python
from bson import ObjectId

class ConversationDocument(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: str
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
        "populate_by_name": True,
    }
```
