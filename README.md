# Production-Grade URL Shortener with Analytics

A high-performance, fault-tolerant URL shortening service built using **FastAPI**, **SQLAlchemy v2**, **Redis**, **RabbitMQ**, **PostgreSQL**, and **Nginx**.

---

## Technical Features

* **Zero-Collision Short Codes**: Sequential atomic Redis counter mapped to a **Base62** encoder (producing clean, sequential, and unique codes with zero collisions).
* **Sliding Window Rate Limiter**: IP-based rate limiting using an atomic **Redis Lua script** (limiting anonymous users to 50 creations per day, with unlimited access for authenticated users).
* **Asynchronous Click Analytics**: Click redirection is optimized for sub-10ms response times. Analytics collection is delegated to a durable **RabbitMQ** broker.
* **Batch Analytics Consumer**: A standalone worker consumes click events from RabbitMQ and performs bulk insertions into PostgreSQL (every 100 events or 5 seconds) to optimize database writing throughput.
* **Security & Auth**: JWT-based access tokens with **Refresh Token Rotation (RTR)** to detect and block token replay attacks.
* **Automatic Cleanup**: **APScheduler** periodic tasks running with a Redis lock to deactivate anonymous URLs that have been inactive for more than 30 days.

---

## Tech Stack

* **Package Manager**: [UV](https://github.com/astral-sh/uv)
* **API Backend**: FastAPI v0.139.0
* **WSGI/ASGI Server**: Gunicorn with Uvicorn workers
* **Database**: PostgreSQL (via asyncpg async dialect) & SQLAlchemy v2
* **Cache & Rate Limiting**: Redis
* **Message Broker**: RabbitMQ
* **Reverse Proxy**: Nginx
* **Migrations**: Alembic

---

## Project Structure

```text
├── alembic/                # Database migration scripts & env
├── docker/                 # Container configs (Dockerfile, nginx.conf, etc.)
│   ├── Dockerfile
│   ├── Dockerfile.worker
│   ├── nginx.conf
│   └── docker-compose.yml
├── src/
│   └── app/
│       ├── api/            # API endpoints (Auth, Links, Stats, Health)
│       ├── core/           # Security, Rate Limiter, Redis, RabbitMQ, Base62
│       ├── db/             # Base declarations & Async Session Factory
│       ├── middleware/     # Request ID tracking
│       ├── models/         # SQLAlchemy models
│       ├── repositories/   # Data Access Object Layer
│       ├── schemas/        # Pydantic schemas
│       ├── services/       # Core Business Logic Layer
│       └── main.py         # Application Entry & Lifespan
├── tests/                  # Pytest integration tests
├── worker/
│   └── consumer.py         # RabbitMQ analytics batch consumer
├── pyproject.toml
└── README.md
```

---

## Setup & Running

### Prerequisites
* [Docker & Docker Compose](https://www.docker.com/get-started)
* [UV](https://github.com/astral-sh/uv) (for running locally)

### Running via Docker Compose
To build and start the entire stack (Nginx, API, Worker, Postgres, Redis, RabbitMQ) completely offline or online:

1. Clone or navigate to the project directory.
2. Initialize environment config (already created):
   ```bash
   cp .env.example .env
   ```
3. Launch the compose services:
   ```bash
   docker compose -f docker/docker-compose.yml up -d --build
   ```
4. Run Alembic migrations to apply tables:
   ```bash
   uv run alembic upgrade head
   ```

The application will be accessible at [http://localhost:8000](http://localhost:8000).

---

## API Documentation

Interactive API documentations are exposed locally through Nginx:
* **Swagger UI**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
* **ReDoc**: [http://localhost:8000/api/redoc](http://localhost:8000/api/redoc)

---

## Testing & Quality Assurance

The project includes an integration test suite verifying end-to-end functionality. Database tables and Redis datasets are automatically truncated/flushed between test runs to guarantee complete isolation.

To run the tests:
```bash
uv run pytest
```
