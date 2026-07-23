# ArtMentor

ArtMentor is an intent-aware critique workspace for digital illustration. An artist uploads a work, states the creative intent, confirms the AI's reading, receives a focused critique across composition, value, color, and visual narrative, then uploads a revision for a before-and-after report.

The MVP is designed as a portfolio, competition, and future research project—not as an autonomous judge of artistic quality. It explicitly records when the artist says an apparent “problem” is an intentional design choice.

## 中文代码阅读指南

如果你想理解项目如何实现，建议先沿着一条完整请求阅读，而不是从文件树逐个看：

```text
App.tsx 页面状态与交互
  → api.ts 统一发送请求
  → main.py 校验会话、图片和参数
  → ai.py 组织 Prompt、调用视觉模型并校验结构化输出
  → schemas.py 定义前后端数据契约
  → models.py 持久化项目、点评、反馈和修改版
  → test_api_flow.py 验证整个闭环
```

| 核心文件 | 负责的功能 |
| --- | --- |
| `frontend/src/App.tsx` | 页面总控和前端状态机：上传、意图确认、点评、反馈、修改版对比 |
| `frontend/src/api.ts` | 前端唯一的 HTTP 请求入口，统一处理 URL、访问码、匿名 Cookie 和错误 |
| `backend/app/main.py` | FastAPI 应用编排层：路由、鉴权、图片处理、AI 调用、数据库写入和静态页面托管 |
| `backend/app/services/ai.py` | AI 供应商适配、Prompt、图片输入、结构化输出校验和离线演示回退 |
| `backend/app/schemas.py` | Pydantic 数据契约，限制模型输出和接口数据的字段、数量与取值范围 |
| `backend/app/models.py` | SQLAlchemy 数据表，保存作品项目、点评快照、用户反馈和修改版报告 |
| `backend/tests/test_api_flow.py` | 不消耗 API 额度的端到端测试，覆盖闭环、数据隔离、访问码和前端托管 |

README 主体保持英文，便于 GitHub 展示；上述核心文件内补有中文模块与关键流程注释。

## What the MVP demonstrates

- Multimodal reasoning through a provider adapter: WildAI / GPTsAPI Chat Completions or the official OpenAI Responses API
- An intent-confirmation gate before critique
- Four-dimensional analysis with at most three high-leverage suggestions
- A reader-first teaching format: one useful art term, a plain-language explanation, a visible goal, and concrete steps
- Editable normalized image annotations rendered with Konva
- Deterministic OpenCV evidence: value, saturation, colorfulness, edge density, focal centroid, and palette
- Three curated public-domain study references with provenance and license links
- Useful / not useful / intentional feedback capture, including the artist's reason
- Revision upload, side-by-side slider, and per-dimension improved / unchanged / tradeoff / uncertain outcomes
- Persistent project history in PostgreSQL (Docker) or SQLite (simple local development)
- Supabase-compatible S3 object storage for deployment, MinIO in Docker, and local disk for development
- Anonymous browser-session isolation, private media access, per-IP limits, and an optional demo access code
- A clearly labeled offline fallback so a live demo still works if the API is unavailable

## Quick start with Docker (recommended)

Requirements: Docker Desktop and either a WildAI / GPTsAPI key or an official OpenAI API key.

```powershell
Copy-Item .env.example .env
# Configure one provider in .env. Never commit the file.
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). FastAPI documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs), and the MinIO console at [http://localhost:9001](http://localhost:9001).

ArtMentor defaults to WildAI / GPTsAPI at `https://api.gptsapi.net/v1`, using its OpenAI-compatible `/chat/completions` endpoint and the vision-capable `gpt-5.6-terra` model. Change the model with `GPTSAPI_MODEL`. The official OpenAI path remains available by setting `AI_PROVIDER=openai`. Keys are read only by the backend and are never embedded in the frontend bundle.

On Windows, the included helper saves a WildAI key without echoing it and preserves any existing official OpenAI key:

```powershell
.\scripts\configure-gptsapi.ps1
```

The model catalog changes over time. If `gpt-5.6-terra` is unavailable for your account, enter another image-capable model ID shown in the WildAI dashboard.

## Local development without Docker

Backend:

```powershell
Copy-Item .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The Vite server proxies `/api` to the backend.

## Tests

Tests deliberately clear both provider keys and use the deterministic fallback, so they never consume API credit.

```powershell
cd backend
pytest -q
ruff check app tests

cd ..\frontend
npm run build
npm run lint
```

## Public-domain examples

The starter catalog contains Hokusai's *The Great Wave*, Vermeer's *Girl with a Pearl Earring*, and Van Gogh's *Wheat Field with Cypresses*. Public-domain study images are bundled for a reliable offline demo; source records link to The Met or Mauritshuis. Each work is marked Public Domain and links to the Public Domain Mark. ArtMentor never presents model-generated images as historical references.

## AI behavior and privacy

- Uploaded images are sent to the selected AI provider when the artist requests the pre-critique visual context check, and again when the artist confirms the context and starts the critique.
- The original and confirmed intent, generated analysis, annotations, feedback, and revision report are stored locally in the configured database/object store.
- `ALLOW_DEMO_FALLBACK=true` catches provider errors and returns labeled deterministic feedback. Set it to `false` when API failures should be explicit.
- WildAI / GPTsAPI is a third-party relay. Its published policy says request content is relayed upstream and is not durably stored by GPTsAPI, but transient fragments may appear in short-term error logs and upstream handling is governed by the selected model provider. Do not upload confidential or unlicensed work without the artist's consent.
- The model is instructed to respect named style and intent, treat stylization as potentially deliberate, avoid precise anatomy diagnosis, and express uncertainty.
- This is educational feedback, not an objective score or a replacement for a human teacher.

See [Architecture](docs/ARCHITECTURE.md), [API](docs/API.md), and [Research roadmap](docs/RESEARCH.md).

For the public deployment path, see [Render + Supabase deployment](docs/DEPLOYMENT.md).

## Project structure

```text
ArtMentor/
├── backend/              FastAPI, AI provider adapters, OpenCV, persistence, tests
├── frontend/             React, TypeScript, Konva, responsive UI
├── docs/                 Architecture, API, research direction
├── data/                 Ignored local uploads/database
└── docker-compose.yml    PostgreSQL + MinIO + backend + frontend
```

## License

Code is released under the MIT License. Referenced artworks retain their source-provided public-domain status and provenance.
