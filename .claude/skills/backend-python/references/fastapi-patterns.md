# FastAPI Patterns

## Route Handler Pattern

```python
from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies import get_service, get_current_user_id
from app.models.schemas import RequestModel, ResponseModel

router = APIRouter(prefix="/api/v1")

@router.post("/endpoint", response_model=ResponseModel)
async def endpoint(
    request: RequestModel,
    user_id: str = Depends(get_current_user_id),
    service: MyService = Depends(get_service),
):
    result = await service.process(request, user_id)
    return ResponseModel(**result)
```

## Dependency Injection

```python
# app/api/dependencies.py
_service_instance = None

def set_service(service):
    global _service_instance
    _service_instance = service

def get_service() -> MyService:
    if _service_instance is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    return _service_instance

def get_current_user_id(request: Request) -> str:
    user_id = request.headers.get("x-user-id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")
    return user_id
```

## Lifespan Pattern

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    service = MyService(settings)
    await service.connect()
    set_service(service)
    yield
    # Shutdown
    await service.disconnect()

app = FastAPI(lifespan=lifespan)
```

## SSE Streaming

```python
from fastapi.responses import StreamingResponse

@router.post("/query/stream")
async def query_stream(request: QueryRequest, ...):
    async def event_generator():
        async for event in service.process_query_stream(...):
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## Error Handling

```python
# Extend from service base exception
class MyServiceError(ChatException):
    pass

# In routes: let FastAPI exception handlers catch
@app.exception_handler(ChatException)
async def handle_service_error(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc)})
```
