# ICSSPulse Light 

## 🔍 Overview

ICSSPulse Light is a **minimal** containerized version of the original tool.

## 🐳 Build & Running

```bash
# Build image
docker-compose build

# Rebuild without cache (clean build)
docker-compose build --no-cache

# Build specific service
docker-compose build icsspulse-light

# Start in background
docker-compose up -d

# Start in foreground (see logs)
docker-compose up

# Start specific service
docker-compose up -d icsspulse-light
```
## 📊 Monitoring

```bash
# View logs
docker-compose logs

# Follow logs in real-time
docker-compose logs -f

# View last 50 lines
docker-compose logs --tail=50

# View specific service logs
docker-compose logs icsspulse-light
```

## 🐛 Debugging

```bash
# Shell access
docker-compose exec icsspulse-light bash

# Run command inside container
docker-compose exec icsspulse-light python -c "import flask; print(flask.__version__)"

# Check running processes
docker-compose exec icsspulse-light ps aux

# Check network connectivity
docker-compose exec icsspulse-light curl <URL>
```


## What's Included

### Current Protocol Controllers (v1.0)

- **Modbus TCP Handler**
- **OPC UA Handler**


### Infrastructure

| Component | Purpose |
|-----------|---------|
| **Flask Application** | Lightweight Python web framework |
| **Docker Container** | Multi-stage optimized image (~200MB) |
| **Docker Compose** | Single-command deployment |
| **Health Checks** | Automatic container monitoring |
| **Logging** | JSON file logging (10MB rotation) |

---

## What's NOT Included

- Network Scanning
- LLM Reporting


---

