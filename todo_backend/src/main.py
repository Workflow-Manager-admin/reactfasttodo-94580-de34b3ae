"""
To-Do List API Backend (FastAPI)
=================================

- Fully RESTful endpoints for /tasks and /tasks/{id} with CRUD and filtering
- SQLite database via SQLAlchemy ORM (auto-create table)
- Pydantic for validation and serialization
- Robust error handling: 404, validation, 500
- CORS enabled (dev: all origins), fit for React frontend
- /, /health and /usage routes for status/info
- PEP8 and organized
- Local dev friendly (DB in file, .env support if extended)
"""

from fastapi import FastAPI, HTTPException, status, Depends, Path, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# --- Database Setup ---

SQLITE_URL = "sqlite:///./todo.sqlite3"
engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class TaskORM(Base):
    """SQLAlchemy model for tasks."""
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(String(1024), default="")
    completed = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)


# --- Pydantic Schemas ---

# PUBLIC_INTERFACE
class TaskBase(BaseModel):
    """Base Task model (shared properties)."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Title of the task"
    )
    description: Optional[str] = Field(
        "",
        max_length=1024,
        description="Task description (optional)"
    )


# PUBLIC_INTERFACE
class TaskCreate(TaskBase):
    """Schema for task creation."""


# PUBLIC_INTERFACE
class TaskUpdate(BaseModel):
    """Schema for PATCH/PUT task updates."""
    title: Optional[str] = Field(
        None, min_length=1, max_length=256, description="New title for the task"
    )
    description: Optional[str] = Field(
        None, max_length=1024, description="New description"
    )
    completed: Optional[bool] = Field(None, description="Set completion status")


# PUBLIC_INTERFACE
class TaskOut(TaskBase):
    """Schema for API response."""

    id: int
    completed: bool

    class Config:
        orm_mode = True


# --- FastAPI App Setup ---

app = FastAPI(
    title="To-Do Task Manager API",
    version="1.0.0",
    description=(
    "Backend for a simple to-do list. Perform CRUD operations on tasks "
    "with full REST endpoints."
),
    openapi_tags=[
        {"name": "Tasks", "description": "Task CRUD operations"},
        {"name": "Health", "description": "Health/status endpoints"},
        {"name": "Help", "description": "Usage examples and project meta"}
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # For dev; restrict to frontend origin in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Dependency ---

# PUBLIC_INTERFACE
def get_db():
    """Yield a database session for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Utility: Get or 404 ---

# PUBLIC_INTERFACE
def get_task_or_404(task_id: int, db: Session) -> TaskORM:
    """Fetch a task by id or raise 404."""
    task = db.query(TaskORM).filter(TaskORM.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task with id={task_id} not found"
        )
    return task


# --- Root and Health Endpoints ---

@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "message": "To-Do backend is running"
    }


# --- Usage and Project Info ---

@app.get("/usage", tags=["Help"])
def usage_notes():
    """Usage, health, and feature notes."""
    return {
        "about": "This is the backend API for a To-Do list web app.",
        "endpoints": [
            {
                "method": "GET",
                "path": "/tasks",
                "desc": "List all tasks, optionally filter by status"
            },
            {
                "method": "POST",
                "path": "/tasks",
                "desc": "Add a new task"
            },
            {
                "method": "GET",
                "path": "/tasks/{id}",
                "desc": "Get a specific task"
            },
            {
                "method": "PUT",
                "path": "/tasks/{id}",
                "desc": "Update all details of a task"
            },
            {
                "method": "PATCH",
                "path": "/tasks/{id}",
                "desc": "Partial update of a task"
            },
            {
                "method": "DELETE",
                "path": "/tasks/{id}",
                "desc": "Delete a task"
            },
        ],
        "filtering": (
            "Use status param on /tasks: ?status=all|completed|incomplete"
        ),
        "visual_feedback": "All error responses return 'visual_feedback': true",
    }


# --- CRUD Endpoints ---

# PUBLIC_INTERFACE
@app.get(
    "/tasks",
    response_model=List[TaskOut],
    tags=["Tasks"],
    summary="List tasks"
)
def list_tasks(
    status: str = Query("all", description="Filter: all/completed/incomplete"),
    db: Session = Depends(get_db)
):
    """
    Fetch all tasks, with optional filter by status.
    """
    q = db.query(TaskORM)
    if status == "completed":
        q = q.filter(TaskORM.completed.is_(True))
    elif status == "incomplete":
        q = q.filter(TaskORM.completed.is_(False))
    tasks = q.order_by(TaskORM.id.desc()).all()
    return tasks


# PUBLIC_INTERFACE
@app.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Tasks"],
    summary="Create task"
)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    """
    Add a new task.
    """
    new_task = TaskORM(
        title=task.title.strip(),
        description=task.description or ""
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


# PUBLIC_INTERFACE
@app.get(
    "/tasks/{task_id}",
    response_model=TaskOut,
    tags=["Tasks"],
    summary="Get task"
)
def get_task(
    task_id: int = Path(..., gt=0, description="Task ID"),
    db: Session = Depends(get_db)
):
    """
    Get task by id.
    """
    task = get_task_or_404(task_id, db)
    return task


# PUBLIC_INTERFACE
@app.put(
    "/tasks/{task_id}",
    response_model=TaskOut,
    tags=["Tasks"],
    summary="Update task (full)"
)
def update_task(
    task_id: int = Path(..., gt=0),
    data: TaskCreate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Fully update (replace) a task by id.
    """
    task = get_task_or_404(task_id, db)
    task.title = data.title.strip()
    task.description = data.description or ""
    db.commit()
    db.refresh(task)
    return task


# PUBLIC_INTERFACE
@app.patch(
    "/tasks/{task_id}",
    response_model=TaskOut,
    tags=["Tasks"],
    summary="Update task (partial)"
)
def patch_task(
    task_id: int = Path(..., gt=0),
    patch: TaskUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Partially update task fields.
    """
    task = get_task_or_404(task_id, db)
    if patch.title is not None:
        task.title = patch.title.strip()
    if patch.description is not None:
        task.description = patch.description
    if patch.completed is not None:
        task.completed = patch.completed
    db.commit()
    db.refresh(task)
    return task


# PUBLIC_INTERFACE
@app.delete(
    "/tasks/{task_id}",
    response_model=dict,
    tags=["Tasks"],
    summary="Delete task"
)
def delete_task(
    task_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete a task.
    """
    task = get_task_or_404(task_id, db)
    db.delete(task)
    db.commit()
    return {
        "ok": True,
        "id": task_id,
        "message": "Task deleted",
        "visual_feedback": True
    }


# --- Custom Error Handlers ---

@app.exception_handler(HTTPException)
def handle_http_exc(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "visual_feedback": True},
    )


@app.exception_handler(Exception)
def handle_generic_exc(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "visual_feedback": True
        }
    )
