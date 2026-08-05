from fastapi import APIRouter
from ..core import load_workflow_steps, save_workflow_steps, WorkflowConfigPayload

router = APIRouter()

@router.get("/workflow/config")
def get_workflow_config():
    statuses = load_workflow_steps()
    return {
        "statuses": statuses,
        "default_status": statuses[0] if statuses else None,
        "uses_default_template": statuses == load_workflow_steps(),
    }


@router.put("/workflow/config")
def update_workflow_config(payload: WorkflowConfigPayload):
    statuses = save_workflow_steps(payload.statuses)
    return {
        "message": "Workflow updated successfully",
        "statuses": statuses,
        "default_status": statuses[0] if statuses else None,
    }


@router.post("/workflow/reset")
def reset_workflow_config():
    statuses = save_workflow_steps(load_workflow_steps())
    return {
        "message": "Workflow reset to default milestones",
        "statuses": statuses,
        "default_status": statuses[0] if statuses else None,
    }
