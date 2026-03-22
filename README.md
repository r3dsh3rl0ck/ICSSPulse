<div align="center">

![logo](/images/icsspulse-logo.png)

### A Modular LLM-Assisted Platform for Industrial Control System Penetration Testing


> **A web-based platform that unifies network scanning, protocol-aware Modbus & OPC UA interaction, and LLM-assisted reporting in a single lightweight ICS pentesting ecosystem.**

</div>



---

## 📖 Table of Contents

- [Overview](#-overview)
- [Features at a Glance](#-features-at-a-glance)
- [Architecture](#-architecture)
- [Penetration Testing Lifecycle Coverage](#-penetration-testing-lifecycle-coverage)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [ICSSPulse Light — Docker Edition](#-icsspulse-light--docker-edition)
- [Usage](#-usage)
  - [Network Scanner](#-network-scanner)
  - [Modbus Handler](#-modbus-handler)
  - [OPC UA Handler](#-opc-ua-handler)
  - [LLM-Assisted Reporting](#-llm-assisted-reporting)
- [OPC UA Certificate Setup](#-opc-ua-certificate-setup)
- [Research Paper](#-research-paper)
- [Disclaimer](#️-disclaimer)

---

## 🔍 Overview

Industrial Control Systems (ICS) form the operational backbone of modern critical infrastructure — energy grids, water treatment plants, transportation networks, and manufacturing facilities. Their increasing network connectivity exposes them to cyber threats that are difficult to study safely under live operational conditions.

**ICSSPulse** a modular, extensible, web-based penetration testing platform that enables safe, reproducible protocol-level security assessments of ICS communication channels. It provides a user-friendly GUI orchestrating enumeration, exploitation, and reporting activities over simulated industrial services, without risking operational continuity.

```
Attacker Perspective Assumed by ICSSPulse
─────────────────────────────────────────────────────────────────────────
  Goal        →  Obtain or manipulate process data via exposed endpoints
  Knowledge   →  Modbus & OPC UA protocol semantics; no device config files
  Skills      →  Protocol probing, enumeration, malformed request crafting
  Capabilities→  Send/receive industrial protocol traffic; read/write registers
  Out of scope→  Firmware attacks, hardware I/O, DoS flooding, lateral movement
```

---

## ⚡ Features at a Glance

| Module | Capability |
|---|---|
| 🌐 **Network Scanner** | Host & port discovery via RustScan (Docker-based) |
| 🔌 **Modbus** | Coil/register enumeration, unit ID scanning, read/write, register range scan |
| 🏭 **OPC UA** | Endpoint discovery, tree browse, variable enumeration, read/write, cert-based security |
| 🤖 **LLM Reporting** | Executive & technical reports via GPT-4o-mini, ICS MITRE ATT&CK mitigations |
| 🔒 **Security** | OPC UA SignAndEncrypt / Sign with Basic256Sha256, persistent certificate storage |
| ⚡ **Performance** | Bulk OPC UA Browse + Read batching — ~230× faster with SignAndEncrypt |
| 📊 **Output** | Structured results, Markdown reports, downloadable findings |

---

## 🏗️ Architecture

### Version 1

![verion1](/images/arch-v1.png)


---

## 🔄 Penetration Testing Lifecycle Coverage

| PT Stage | ICSSPulse Support | Coverage |
|---|---|:---:|
| **Planning & Reconnaissance** | Configure targets, ports, protocols, auth via GUI | ✅ Full |
| **Scanning & Enumeration** | RustScan host/port discovery + Modbus unit ID & register mapping + OPC UA node traversal | ✅ Full |
| **Vulnerability Analysis** | Structured output exposes unauthenticated access & insecure configurations | ⚠️ Manual |
| **Exploitation** | Modbus coil/register read/write & malformed requests; OPC UA node read/write | ✅ Full |
| **Post-Exploitation** | Visual state-change feedback from protocol manipulation | ⚠️ Partial |
| **Reporting & Remediation** | LLM-generated executive + technical reports with ATT&CK mitigations | ✅ Full |

---

## 📋 Requirements

```
Python          >= 3.9
Flask           >= 2.x
pymodbus        >= 3.x
python-opcua    >= 0.9.x
openai          >= 1.x
Docker          (for RustScan network scanning)
```

> **Optional:** An OpenAI API key for the LLM reporting module.

---

## 🚀 Installation - Full Version

```bash
# 1. Clone the repository
git clone https://github.com/r3dsh3rl0ck/ICSSPulse-Public.git
cd ICSSPulse-Public

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Pull the RustScan Docker image (required for network scanning)
docker pull rustscan/rustscan:latest

# 5. Set your OpenAI API key (required for LLM reporting)
export OPENAI_API_KEY="sk-..."    # Linux / macOS
# set OPENAI_API_KEY=sk-...       # Windows

# 6. Launch ICSSPulse
python app.py
```

Then open your browser at **`http://127.0.0.1:5000`**.

---

## 🐳 ICSSPulse Light — Docker Edition

A minimal, self-contained containerised version of ICSSPulse. No Python environment setup required — just Docker.

> **Includes:** Modbus TCP Handler · OPC UA Handler  
> **Excludes:** Network Scanner · LLM Reporting

```bash
cd icsspulse-light
# Follow the instructions there
```

## 🔧 Usage

### 🌐 Network Scanner

Powered by **RustScan** inside a Docker container for accurate, fast host and port discovery.

| Parameter | Description | Default |
|---|---|---|
| Target / Range | IP address or CIDR range | — |
| Port Range | Ports to scan | `1-65535` |
| Timeout | Per-port timeout (ms) | `3000` |

Results are automatically forwarded to the **reporting inbox** for inclusion in LLM-generated reports.

---

### 🔌 Modbus Handler

Full-stack Modbus TCP interaction via **pymodbus**, covering all four primary data types.

| Data Type | Access | Description |
|---|---|---|
| **Coils** | R/W | Single-bit digital outputs |
| **Discrete Inputs** | R | Single-bit digital inputs |
| **Holding Registers** | R/W | 16-bit analog/control values |
| **Input Registers** | R | 16-bit analog sensor values |

**Available operations:**

```
• Unit ID Scan      — probe a range of slave IDs for active Modbus devices
• Register Range    — enumerate memory regions in configurable chunks (default 1000)
• Enumerate         — read all accessible values across a data type
• Read              — targeted single-address retrieval
• Write             — modify a coil or register value
```

**Key parameters:** target IP, port (default `502`), unit/slave ID, address, quantity, timeout, retries.

---

### 🏭 OPC UA Handler

Protocol-aware OPC UA interaction via **python-opcua**, with performance-optimised bulk operations.

#### Actions

| Action | Description |
|---|---|
| **Discover Endpoints** | List all server endpoints, security modes, and token types |
| **Browse (Tree)** | Traverse the namespace tree with ASCII tree output |
| **Enumerate Variables** | List all Variable nodes with data type, access level, and value |
| **Readable Variables Only** | Filter by `AccessLevel & CurrentRead` |
| **Writable Variables Only** | Filter by `AccessLevel & CurrentWrite` |
| **Read** | Read current value of a node by NodeId (e.g., `ns=2;i=10`) |
| **Write** | Write a new value to a node by NodeId |

#### Performance

ICSSPulse uses **two-phase bulk OPC UA operations** that are critical for encrypted connections:

```
Phase 1 — Batched BFS Browse   (50 nodes per Browse request)
  → NodeClass, BrowseName, DisplayName arrive FREE in every Browse response

Phase 2 — Chunked Bulk Read    (100 nodes per Read request)
  → DataType, AccessLevel, UserAccessLevel, Value packed in one encrypted message

  Old sequential code:  200 nodes × 7 calls = 1,400 round-trips ≈ 14 s
  New bulk code:        ceil(200/50) + ceil(200/100) = 6  round-trips ≈  0.1 s
```

#### Security Modes

| Mode | SecurityPolicy | Certificate Required |
|---|---|:---:|
| `None` | — | ❌ |
| `Sign` | Basic256Sha256 | ✅ |
| `SignAndEncrypt` | Basic256Sha256 | ✅ |

---

### 🤖 LLM-Assisted Reporting

ICSSPulse automatically aggregates all testing artefacts into an **LLM-generated report** using GPT-4o-mini.

**Two report modes:**

| Mode | Audience | Content |
|---|---|---|
| **Executive** | Management / Decision-makers | High-level risk overview, business impact |
| **Technical** | Security analysts / Practitioners | Protocol traces, node enumeration, register maps, mitigations |

All mitigations are mapped to the **[ICS MITRE ATT&CK matrix](https://attack.mitre.org/matrices/ics/)** and consolidated into a single, non-redundant section. Reports are rendered in **Markdown** in the GUI and available for download.

```
Testing Session
     │
     ├── Network Scan results  ──┐
     ├── Modbus interactions   ──┼──► Reporting Inbox (JSON)
     └── OPC UA interactions   ──┘          │
                                            ▼
                               Extract hosts, ports, unit IDs,
                               registers, node IDs, access flags
                                            │
                                            ▼
                               Map findings → ICS ATT&CK mitigations
                                            │
                                            ▼
                               GPT-4o-mini  →  Executive / Technical Report
                                            │
                                            ▼
                               Markdown rendered in GUI  →  Download
```

---

## 🔒 OPC UA Certificate Setup

To use **Sign** or **SignAndEncrypt** security modes, generate a self-signed client certificate:

```bash
# Step 1 — Generate private key and self-signed certificate
# The subjectAltName URI must match the "Application URI" field in the GUI
openssl req -x509 -newkey rsa:2048 \
  -keyout client_key.pem \
  -out client_cert.pem \
  -days 365 -nodes \
  -addext "subjectAltName = URI:urn:ctf:python-opcua-client"

# Step 2 — Convert certificate to DER format (required by the OPC UA handler)
openssl x509 -outform der -in client_cert.pem -out client_cert.der
```

Then in the **ICSSPulse GUI**:

1. Select **Security Mode** → `Sign` or `SignAndEncrypt`
2. Upload `client_cert.der` via the **Client Certificate** field
3. Upload `client_key.pem` via the **Private Key** field
4. Set **Application URI** to match the `subjectAltName` used above

> **Certificates are stored persistently on the server** and reused across sessions until you click **✕ Remove**. The server must trust your certificate (add it to the server's trust store beforehand).



---

## 📄 Research Paper

📎 **Preprint:** [arXiv:2602.20663](https://arxiv.org/abs/2602.20663)

---

## ⚠️ Disclaimer

> **ICSSPulse is intended strictly for authorised security testing, academic research, and educational use in controlled laboratory environments.**
>
> Running ICSSPulse against systems you do not own or lack explicit written permission to test is **illegal** and may violate computer fraud and abuse laws in your jurisdiction. The authors and contributors accept no liability for misuse of this tool. Always obtain proper authorisation before conducting any penetration test.
>
> ICSSPulse does **not** model physical disruptions, controller reprogramming, multi-stage ICS kill chains, or denial-of-service attacks. It is designed for safe, transparent, and reproducible protocol-level experimentation only.

---

