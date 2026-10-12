# AegisFlow — Incident Processing & Recovery Platform

AegisFlow is a Python-based backend platform for processing incidents through persistent jobs, tracking execution progress, and managing failures through a structured job lifecycle.

The project explores reliability engineering concepts such as persistent job storage, pipeline checkpoints, stage-output persistence, audit trails, and controlled recovery.

## Key Features

- **Incident Processing API** — Expose backend endpoints for incident-processing workflows.
- **Persistent Job Management** — Track jobs across queued, running, completed, and failed states.
- **Pipeline Checkpoints** — Persist execution progress to support recovery analysis.
- **Stage-Output Persistence** — Store outputs from completed pipeline stages for later inspection and potential reuse.
- **Failure Handling** — Record processing failures and maintain job lifecycle state.
- **Recovery Safeguards** — Handle interrupted jobs conservatively rather than automatically restarting potentially unsafe operations.
- **Automated Testing** — Use pytest to validate application behavior and reduce regressions.
- **Auditability** — Maintain incident and lifecycle records for traceability.

> Note: Explicit retry endpoints, retry limits, concurrency guarantees, and retry-specific audit events should only be considered supported once implemented and verified by tests.

## Architecture

```text
Client
  |
  v
FastAPI Application
  |
  v
Incident Job Management
  |
  +----> Persistent Job Store
  |
  +----> Incident Processing Pipeline
  |          |
  |          +----> Investigation
  |          +----> Assessment
  |          +----> Remediation Planning
  |
  +----> Pipeline Checkpoints
  |
  +----> Persisted Stage Outputs
  |
  +----> Audit and Lifecycle Records
```

The pipeline separates incident analysis from remediation execution. Planning a remediation action does not, by itself, execute that action.

## Technology Stack

- **Language:** Python
- **API Framework:** FastAPI
- **Testing:** pytest
- **Persistence:** SQLite
- **API Documentation:** OpenAPI / Swagger UI
- **Version Control:** Git and GitHub

## Project Structure

```text
AegisFlow/
├── app/
│   ├── main.py
│   ├── jobs/
│   │   └── incident_jobs.py
│   └── storage/
│       ├── job_store.py
│       └── audit_store.py
├── tests/
├── data/
├── scripts/
├── .gitignore
├── README.md
└── requirements.txt
```

The exact structure may vary as the project evolves.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/AegisFlow.git
cd AegisFlow
```

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use the environment's Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

If the project uses a different dependency file, follow the installation instructions provided in that file.

### 4. Initialize the database

If the repository contains a database initialization script, run the command appropriate to its location. For example:

```powershell
python -m scripts.init_db
```

This command assumes `scripts/init_db.py` exists and supports module execution.

### 5. Start the API

```powershell
python -m uvicorn app.main:app --reload
```

The local API should be available at:

- API root: http://127.0.0.1:8000/
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

These addresses assume the application starts on the default Uvicorn port.

## Running Tests

Run the full automated test suite:

```powershell
python -m pytest -v
```

For a concise test summary:

```powershell
python -m pytest -q
```

Run tests before committing changes so regressions are caught early.

## Job Lifecycle

AegisFlow uses a persistent job lifecycle to represent incident-processing progress.

| State | Meaning |
|---|---|
| `queued` | Waiting for processing |
| `running` | Processing is in progress |
| `completed` | Processing finished successfully |
| `failed` | Processing stopped because of an error or interruption |

Persisted checkpoints and stage outputs provide visibility into completed work. Recovery behavior must remain conservative when the safety of resuming a partially completed operation cannot be established.

## Reliability and Safety Principles

- Persist job state instead of relying exclusively on in-memory state.
- Record pipeline progress for debugging and recovery analysis.
- Distinguish remediation planning from remediation execution.
- Avoid blindly replaying operations after process restarts.
- Validate lifecycle transitions and failure behavior with automated tests.
- Keep credentials, environment files, and local runtime databases out of public version control.

## Engineering Goals

AegisFlow is designed to explore practical backend engineering challenges, including:

- Asynchronous job processing
- Durable state management
- Failure recovery and idempotency
- Pipeline observability
- Automated testing
- API design and maintainability

## Future Improvements

Potential extensions include:

- Explicit, bounded retry policies
- Atomic retry-state transitions
- Retry and lifecycle audit events
- Concurrency and idempotency integration tests
- Structured logging and operational metrics
- Containerized deployment and CI workflows

These are roadmap items unless the corresponding functionality is already implemented and tested.

## Disclaimer

AegisFlow is a software engineering project for learning and demonstrating backend reliability concepts. It should not be used to automatically execute production remediation actions without appropriate authorization, safeguards, and operational testing.

## Author

**Yash Kalbhile**

GitHub: https://github.com/yash45615

