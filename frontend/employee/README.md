# Employee Frontend

This package owns the Employee frontend entrypoint.

Employee document records and actions intentionally use the shared permission-aware workspace implementation from `frontend/frontend_admin`. That keeps the document model and API behavior identical for administrators and employees while `has_permission()` controls which employee actions are available.

Run independently with:

```text
.venv\Scripts\python.exe run_flet_employee.py
```

The default browser port is `8552` (`EMPLOYEE_FRONTEND_PORT` can override it).
