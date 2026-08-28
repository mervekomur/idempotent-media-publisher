iIdempotent & Fault-Tolerant Media Publisher API

A production-ready, highly scalable media publishing microservice built with Python, FastAPI, PostgreSQL, Redis, and Celery. This architecture ensures exact-once processing via idempotency locks, asynchronous background task execution, and robust error handling under high concurrency.
🏗️ Architecture & Core Mechanisms

The project is structured following Clean Architecture principles, separating concerns into distinct, testable layers:

    domain: Pydantic schemas for data validation and SQLAlchemy ORM models representing the core business entities.

    infrastructure: Database connection management (database.py) and Redis distributed caching/locking (cache.py).

    api: FastAPI routers, dependency injection (dependencies.py), and idempotency middleware (middleware.py).

    services: Celery background workers (worker.py) handling non-blocking heavy lifting (e.g., external API integrations, media processing).

Key Features

    Distributed Idempotency: Uses Redis SETNX mechanism and custom headers (x-idempotency-key) to prevent duplicate processing of identical requests, returning a 409 Conflict on concurrent retries.

    Asynchronous Processing: Offloads heavy publishing workflows to Celery workers backed by Redis, responding instantly to clients with a 202 Accepted status.

    Fault Tolerance & Resilience: Implements database transaction management with rollback safety and handles unique constraint violations gracefully to ensure system stability.

    Containerized Orchestration: Fully orchestrated via Docker and Docker Compose, managing API, worker, database, and cache containers in a single network.

🛠️ Tech Stack

    Backend: Python 3.11, FastAPI, Uvicorn

    Database & ORM: PostgreSQL 15, SQLAlchemy

    Asynchronous Queue & Broker: Celery, Redis

    Validation & Settings: Pydantic, Pydantic-Settings

    Deployment: Docker, Docker Compose

🚀 Getting Started
Prerequisites

Make sure you have Docker and Docker Compose installed on your machine.
1. Installation & Running

    Clone the repository:
   1. Clone the repository:
   git clone [idempotent-media-publisher repository](https://github.com/mervekomur/idempotent-media-publisher.git)
   cd idempotent-media-publisher
2. Run with Docker Compose:
   Build and start all services (PostgreSQL, Redis, FastAPI, and Celery Worker) in detached mode:
   docker-compose up --build -d
3. Access the API Documentation:
   Open your browser and navigate to the interactive Swagger UI:

    http://localhost:8000/docs

🧪 Testing the API

   1. Go to /api/v1/publish via the Swagger UI (/docs).

   2. Click Try it out.

   3. Provide a unique transaction key in the header:

        x-idempotency-key: your-unique-uuid-or-string-1

   4. Provide the payload in the request body:
   {
  "media_url": "https://example.com/media/photo.jpg",
  "caption": "Production-ready automated post."
}
   5. Execute the request to receive a 202 Accepted response while the worker processes the task asynchronously in the background. Subsequent requests with the same idempotency key will trigger conflict protection.

📂 Project Structure
```text
idempotent-media-publisher/
├── app/
│   ├── api/          # Routers, dependencies, and middleware
│   ├── core/         # Configuration and environment settings
│   ├── domain/       # SQLAlchemy models and Pydantic schemas
│   ├── infrastructure/# Database sessions and Redis client
│   ├── services/     # Celery worker application and tasks
│   └── main.py       # FastAPI application entrypoint
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
