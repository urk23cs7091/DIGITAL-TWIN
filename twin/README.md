# AuraTwin: Autonomous Cardiovascular Digital Twin & 24/7 Wearable RPM Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-v3.4-38B2AC?logo=tailwind-css&logoColor=white)](https://tailwindcss.com)
[![License](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![Security](https://img.shields.io/badge/HIPAA-Security%20Enforced-indigo.svg)](#security--governance)

**AuraTwin** is a high-performance clinical digital twin platform and autonomous remote patient monitoring (RPM) operating system designed for continuous 24/7 wearable sensor telemetry, real-time hemodynamic state estimation, and automated clinical alarm triage.

---

## Quickstart Guide

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the application server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to **`http://localhost:8000`**.

### Running Automated Test Suite

```bash
pytest -q
```

---

## Default System Credentials

| Role | Default Username | Default Password | Workspace Scope |
| :--- | :--- | :--- | :--- |
| **Clinician** | `clinician` | `demo123` | Remote Patient Monitoring, Alert Triage & Acknowledgment, Smartwatch Telemetry Stream, What-If Lab |
| **Admin** | `admin` | `demo123` | Superuser Access, System Telemetry Pipeline, Exclusive Access to the HIPAA Audit Log (`/audit`) |
| **Researcher** | `researcher` | `demo123` | 64-Dim Latent Heatmap, RGCN Knowledge Graph, Counterfactual Simulation Lab, Occlusion Explainability |
| **Patient** | `patient` | `demo123` | Personalized "My Live Vitals" Dashboard, Personal Health History for `P001`, FHIR R4 Bundle Export |

---

## Project Structure

```
twin/
├── Dockerfile          # Production Docker configuration
├── README.md           # Application documentation
├── requirements.txt    # Python dependencies (FastAPI, uvicorn, pytest)
├── app/
│   ├── __init__.py
│   ├── core.py         # SQLite engine, PBKDF2 hashing, JWT (HS256), HIPAA audit log
│   ├── services.py     # State vector derivation, risk corridors, simulations
│   ├── services_ext.py # RGCN graph generator, FHIR R4 builder, explainability
│   └── main.py         # FastAPI application, WebSocket telemetry, RBAC routes
├── static/
│   └── index.html      # Responsive Single Page Application, Tailwind CSS, Chart.js
└── tests/
    └── test_flow.py    # Automated test suite for end-to-end flow & RBAC barriers
```
