# idempotent-media-publisher
An idempotent publishing engine built with FastAPI, Redis, and PostgreSQL to prevent duplicate submissions and state corruption during network flickers. ||  Ağ gecikmelerinde çift istek ve veri kaybını önleyen, Redis distributed lock ve idempotency middleware tabanlı dayanıklı içerik yayınlama mimarisi.
# 🛡️ Idempotent Media Publisher

> A fault-tolerant, modular backend pipeline designed to eliminate race conditions, double-submissions, and partial-state corruptions in distributed systems.

---

## 📌 The Problem

In high-latency mobile and web environments, network flickers often cause users to click "Publish" multiple times. Without robust backend idempotency:
* **Race conditions** trigger duplicate posts.
* **Partial failures** result in desynchronized state (e.g., media uploaded without its corresponding caption).
* **Silent overrides** leave inconsistent resources in production.

## 🏗️ Architecture & Modular Design

This project is built strictly on **Modular / Clean Architecture** principles to separate concerns, ensure testability, and isolate failures. 

```text
idempotent-media-publisher/
├── app/
│   ├── api/          # Dependency injection and HTTP endpoints
│   ├── core/         # Centralized configuration and error handling
│   ├── domain/       # Pydantic schemas and SQLAlchemy models
│   ├── infrastructure/ # Redis (Locking) and PostgreSQL connections
│   └── services/     # Business logic and atomic Celery workers

Core Mechanisms

    API Gateway (FastAPI): Intercepts requests and extracts the X-Idempotency-Key.

    Distributed Locking (Redis): Uses SETNX with TTL to guarantee that concurrent requests with the same key are blocked or returned with cached states.

    Transactional State (PostgreSQL): Manages the lifecycle of a post (PENDING -> PROCESSING -> COMPLETED/FAILED).

    Asynchronous Workers (Celery): Handles media validation and atomic metadata binding in the background.

🚀 Tech Stack

    Framework: FastAPI (Python 3.10+)

    Database: PostgreSQL (SQLAlchemy + asyncpg)

    Cache & Message Broker: Redis

    Task Queue: Celery

    Deployment: Docker & Docker Compose

🛠️ Quickstart

Clone the repository and spin up the modular infrastructure using Docker:
git clone [https://github.com/yourusername/idempotent-media-publisher.git](https://github.com/yourusername/idempotent-media-publisher.git)
cd idempotent-media-publisher
docker-compose up --build

The API documentation (Swagger UI) will be automatically available at http://localhost:8000/docs.

🧪 Concurrency Testing

To prove the system's fault tolerance against race conditions, run the automated test suite:
pytest tests/test_concurrency.py -v

Simulates 50+ simultaneous requests to verify that only a single database record is created while others receive a 409 Conflict.

