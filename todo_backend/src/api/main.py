"""
FastAPI To-Do App Backend

- RESTful API for Tasks: supports CRUD operations, toggle-complete, and optional status filtering
- SQL (SQLite) database for task persistence via SQLAlchemy
- Pydantic models for validation
- OpenAPI metadata and endpoint docs
- CORS enabled for frontend
- Robust error handling and visual feedback support
"""

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    status,
    Query,
    Path,
    Body,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Database setup
DATABASE_URL = "sqlite:///./db.sqlite3"  # Change this in production / use env vars
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class TaskModel(Base):
    """SQLAlchemy model for tasks (DB table)."""
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(String(1024), default="")
    completed = Column(Boolean, default=False)


# Create tables if not exist
Base.metadata.create_all(bind=engine)


# --------- Pydantic Schemas ---------


# PUBLIC_INTERFACE
class TaskBase(BaseModel):
    """Base schema for Task input/output."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Title of the task"
    )
    description: Optional[str] = Field(
        "",
        max_length=1024,
        description="Optional task description"
    )


# PUBLIC_INTERFACE
class TaskCreate(TaskBase):
    """Schema for creating new tasks."""
    pass


# PUBLIC_INTERFACE
class TaskUpdate(BaseModel):
    """Schema for updating tasks PATCH/PUT."""
    title: Optional[str] = Field(
        None, min_length=1, max_length=256, description="Title to update"
    )
    description: Optional[str] = Field(
        None, max_length=1024, description="Description to update"
    )
    completed: Optional[bool] = Field(
        None, description="Completion status to update"
    )


# PUBLIC_INTERFACE
class TaskToggle(BaseModel):
    """Schema for toggling task state."""
    completed: Optional[bool] = Field(
        None, description="Target state for completion (True/False)"
    )


# PUBLIC_INTERFACE
class TaskOut(TaskBase):
    """Schema for outputting a task with ID and status."""
    id: int
    completed: bool

    class Config:
        orm_mode = True


# ----------- Utility Functions -----------


# PUBLIC_INTERFACE
def get_db():
    """Yield a database session (for FastAPI dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# PUBLIC_INTERFACE
def get_task_or_404(task_id: int, db: Session) -> TaskModel:
    """Get a single task by ID or raise 404 error."""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if task is None:
        raise HTTPException(
            status_code=404, detail=f"Task with id={task_id} not found"
        )
    return task


# ---------- FastAPI App + Swagger tags -----------


app = FastAPI(
    title="To-Do API",
    description=(
        "RESTful API backend for a to-do list application. "
        "Manage tasks with CRUD endpoints and toggle completion."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "Tasks", "description": "Task CRUD and to-do management"},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Use ["http://localhost:3000"] for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------- Health check -----------


@app.get("/", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}


# ----------- Task Endpoints -----------


# PUBLIC_INTERFACE
@app.get(
    "/tasks",
    response_model=List[TaskOut],
    summary="List tasks",
    description=(
        "Retrieve a list of all tasks. Optionally filter by completion status "
        "using the 'status' query parameter ('all', 'completed', 'incomplete')."
    ),
    tags=["Tasks"],
)
def list_tasks(
    status: Optional[str] = Query(
        "all",
        description="Task status filter: 'all'|'completed'|'incomplete'"
    ),
    db: Session = Depends(get_db),
):
    query = db.query(TaskModel)
    if status == "completed":
        query = query.filter(TaskModel.completed.is_(True))
    elif status == "incomplete":
        query = query.filter(TaskModel.completed.is_(False))
    tasks = query.order_by(TaskModel.id.desc()).all()
    return tasks


# PUBLIC_INTERFACE
@app.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create task",
    description="Add a new task. Requires a title (nonempty). Description is optional.",
    tags=["Tasks"]
)
def create_task(
    task: TaskCreate = Body(...),
    db: Session = Depends(get_db)
):
    new_task = TaskModel(title=task.title.strip(), description=task.description or "")
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


# PUBLIC_INTERFACE
@app.get(
    "/tasks/{task_id}",
    response_model=TaskOut,
    summary="Get task",
    description="Retrieve a specific task by its ID.",
    tags=["Tasks"]
)
def get_task(
    task_id: int = Path(..., ge=1, description="ID of the task to retrieve"),
    db: Session = Depends(get_db)
):
    task = get_task_or_404(task_id, db)
    return task


# PUBLIC_INTERFACE
@app.put(
    "/tasks/{task_id}",
    response_model=TaskOut,
    summary="Update task (full)",
    description=(
        "Update all fields of a task (title and description). "
        "Sets completed to False if not provided."
    ),
    tags=["Tasks"]
)
def update_task(
    task_id: int = Path(..., ge=1, description="ID of the task to update"),
    updated: TaskCreate = Body(...),
    db: Session = Depends(get_db)
):
    task = get_task_or_404(task_id, db)
    task.title = updated.title.strip()
    task.description = updated.description or ""
    db.commit()
    db.refresh(task)
    return task


# PUBLIC_INTERFACE
@app.patch(
    "/tasks/{task_id}",
    response_model=TaskOut,
    summary="Update task (partial)",
    description=(
        "Partially update a task (one or more fields: title, description, completed)."
    ),
    tags=["Tasks"]
)
def patch_task(
    task_id: int = Path(..., ge=1, description="ID of the task to update"),
    update: TaskUpdate = Body(...),
    db: Session = Depends(get_db)
):
    task = get_task_or_404(task_id, db)
    if update.title is not None:
        task.title = update.title.strip()
    if update.description is not None:
        task.description = update.description
    if update.completed is not None:
        task.completed = update.completed
    db.commit()
    db.refresh(task)
    return task


# PUBLIC_INTERFACE
@app.patch(
    "/tasks/{task_id}/toggle",
    response_model=TaskOut,
    summary="Toggle task completion",
    description=(
        "Toggle the completion status of a task. "
        "Optionally set to a specific state via JSON body."
    ),
    tags=["Tasks"]
)
def toggle_task(
    task_id: int = Path(..., ge=1, description="ID of the task to toggle"),
    toggle: TaskToggle = Body(
        {},
        description=(
            "Target state for 'completed', or empty for toggling"
        ),
    ),
    db: Session = Depends(get_db)
):
    task = get_task_or_404(task_id, db)
    # If completed field provided, set it to that, else toggle
    if toggle.completed is not None:
        task.completed = toggle.completed
    else:
        task.completed = not task.completed
    db.commit()
    db.refresh(task)
    return task


# PUBLIC_INTERFACE
@app.delete(
    "/tasks/{task_id}",
    response_model=dict,
    summary="Delete task",
    description="Remove a task by ID.",
    tags=["Tasks"]
)
def delete_task(
    task_id: int = Path(..., ge=1, description="ID of the task to delete"),
    db: Session = Depends(get_db)
):
    task = get_task_or_404(task_id, db)
    db.delete(task)
    db.commit()
    return {"ok": True, "id": task_id, "message": "Task deleted"}


# Error handlers for visual feedback


@app.exception_handler(HTTPException)
def custom_http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "visual_feedback": True},
    )


@app.exception_handler(Exception)
def catch_all_error_handler(request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "visual_feedback": True
        },
    )


# Sample usage notes route for API docs


@app.get("/usage", tags=["Help"], summary="API usage notes")
def api_usage_notes():
    return {
        "info": (
            "Use RESTful endpoints under /tasks for all CRUD/task operations. "
            "Supports CORS for frontend on all endpoints. For more info,"
            " see /docs."
        ),
        "examples": {
            "list": {"method": "GET", "url": "/tasks"},
            "create": {
                "method": "POST",
                "url": "/tasks",
                "body": {"title": "Buy milk"}
            },
            "toggle": {
                "method": "PATCH",
                "url": "/tasks/1/toggle"
            },
        },
    }
