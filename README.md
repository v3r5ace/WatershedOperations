# Watershed Operations

Internal church operations dashboard for maintenance punch lists, assignments, and public calendar intake.

## What is included

- FastAPI web app with a login-first experience
- Role-based access control on API endpoints
- SQLite database stored locally in `./data`
- Maintenance task tracking and assignment management
- ICS calendar ingestion for upcoming church events
- Docker packaging for Unraid deployment
- GitHub Actions workflow for publishing images to GitHub Container Registry

## Roles

- `admin`: full access, including user creation and all task/calendar actions
- `manager`: can create and update tasks and sync calendar events
- `staff`: can view assigned tasks and update their own task status
- `viewer`: read-only dashboard access

## Local development

1. Copy `.env.example` to `.env`.
2. Change `SECRET_KEY`, `DEFAULT_ADMIN_EMAIL`, and `DEFAULT_ADMIN_PASSWORD`.
3. Optionally set `CALENDAR_ICS_URL` to your church's public ICS feed.
4. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The site runs on [http://localhost:8000](http://localhost:8000) in development or port `8080` in Docker.

## Docker

Build locally:

```bash
docker build -t watershed-operations .
docker run --rm -p 8080:8080 --env-file .env -v "$(pwd)/data:/app/data" watershed-operations
```

For Unraid, map `/app/data` to a persistent appdata folder so the SQLite database survives container updates.

## GitHub Container Registry

The workflow at `.github/workflows/docker-publish.yml` publishes on pushes to `main`.

Your Unraid image name will be:

```text
ghcr.io/<github-owner>/<repository>:latest
```

If the package is private, create a GitHub personal access token in Unraid with permission to read packages.

## Calendar ingestion

Set `CALENDAR_ICS_URL` to a public `.ics` feed. Managers and admins can trigger an import through `POST /api/events/sync` or from the dashboard button.

## Default login

On first launch, the app seeds one admin account using:

- `DEFAULT_ADMIN_EMAIL`
- `DEFAULT_ADMIN_PASSWORD`

Change those values before your first production deployment.
