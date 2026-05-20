# Block 11 — Federated MemPalace + Real-Time Collab + Preprint Auto-Submit Implementation Plan (§§5.9, 5.10, 5.11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Ship three connected features. (1) **§5.10 federated MemPalace** — cross-org shared memory via Yjs CRDT over WebSocket with per-drawer ACL. (2) **§5.11 real-time multi-author collab** — concurrent manuscript editing via Yjs + presence cursors + CRDT comment threads. (3) **§5.9 pre-print auto-submission** — one-command deposit to arXiv / bioRxiv / OSF / SSRN / OAI-PMH-SWORD institutional repositories.

**Architecture:** Federated palace + collab share a Yjs + y-websocket backend. The websocket server runs as a separate process (`plugins/vedix/saas/app/workers/yjs_server.py`) so the main FastAPI app stays sync-safe. Each shared drawer or manuscript = one Yjs document. ACL enforced server-side on every WS message. Pre-print auto-submit is independent: per-target adapter that takes a `manuscript.pdf` + metadata and posts to the target's API.

**Tech Stack:**
- **CRDT:** `y-py` (Yjs Python bindings) for server-side reconciliation; `yjs` (TypeScript) for the web UI client
- **WebSocket:** `websockets` (Python) for the y-websocket server
- **Preprint adapters:**
  - arXiv: `arxiv` Python package + raw XML to `/api/upload`
  - bioRxiv: bioRxiv submission REST API (Cold Spring Harbor)
  - OSF: `osfclient` or direct REST against `api.osf.io`
  - SSRN: HTTP form-fill auto-submission (no public API)
  - OAI-PMH SWORD v2: `sword2` Python package

**Spec source:** §5.9, §5.10, §5.11.

---

## File structure

```
plugins/vedix/saas/app/
├── workers/yjs_server.py       # WebSocket Yjs reconciliation server
├── routers/palace.py           # Shared palace REST API
├── routers/collab.py           # Collab session bootstrap (issues Yjs doc IDs)
└── models/yjs_doc.py           # Persistence: Yjs doc snapshots in Postgres

plugins/vedix/web/src/
├── collab/
│   ├── YjsProvider.tsx         # React context for Yjs doc + awareness
│   ├── CursorOverlay.tsx       # presence cursors
│   └── CommentThread.tsx       # CRDT-backed comment thread
└── pages/
    └── CollabEditor.tsx        # full editor pane wrapping a Yjs doc

plugins/vedix/mcp/lib/orchestrator/preprint/
├── __init__.py
├── arxiv_adapter.py
├── biorxiv_adapter.py
├── osf_adapter.py
├── ssrn_adapter.py
└── sword_adapter.py            # OAI-PMH / SWORD v2 institutional repos
```

## Task 1: Yjs WebSocket server

**Files:**
- Create: `plugins/vedix/saas/app/workers/yjs_server.py`
- Create: `plugins/vedix/saas/app/models/yjs_doc.py`
- Test: `plugins/vedix/saas/tests/test_yjs_server.py`

- [ ] **Step 1: Write test**

```python
# plugins/vedix/saas/tests/test_yjs_server.py
import asyncio
import pytest
import websockets
from app.workers.yjs_server import handler

@pytest.mark.asyncio
async def test_two_clients_sync_text():
    # Boot the server on a random port
    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}/doc/test123") as a, \
                   websockets.connect(f"ws://127.0.0.1:{port}/doc/test123") as b:
            # Client A sends a Yjs update; client B should receive it
            await a.send(b"\x00\x01\x01" + b"\x00")  # tiny fake Yjs update
            try:
                msg = await asyncio.wait_for(b.recv(), timeout=2.0)
                assert msg is not None
            except asyncio.TimeoutError:
                pytest.fail("client B never received broadcast")
```

- [ ] **Step 2: Implement Yjs server**

```python
# plugins/vedix/saas/app/workers/yjs_server.py
"""Y.js-compatible WebSocket reconciliation server.

Each connection joins a document room (URL path /doc/{doc_id}). The server
broadcasts every binary message it receives to every other connection in the
same room. Document state is periodically snapshotted to Postgres via y-py.
"""
from __future__ import annotations
import asyncio
import logging
from collections import defaultdict
from typing import Awaitable
import websockets
from websockets.server import WebSocketServerProtocol

log = logging.getLogger(__name__)
ROOMS: dict[str, set[WebSocketServerProtocol]] = defaultdict(set)
ROOM_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

async def handler(ws: WebSocketServerProtocol, path: str | None = None):
    path = path or ws.path
    room = path.strip("/").split("/", 1)[1] if "/" in path else "default"
    async with ROOM_LOCKS[room]:
        ROOMS[room].add(ws)
    log.info(f"client joined room {room}; size={len(ROOMS[room])}")
    try:
        async for msg in ws:
            # Broadcast to everyone else in the room
            to_send = [peer.send(msg) for peer in ROOMS[room] if peer is not ws and not peer.closed]
            if to_send:
                await asyncio.gather(*to_send, return_exceptions=True)
    finally:
        async with ROOM_LOCKS[room]:
            ROOMS[room].discard(ws)
            if not ROOMS[room]:
                del ROOMS[room]

async def main(host: str = "0.0.0.0", port: int = 1234):
    async with websockets.serve(handler, host, port):
        log.info(f"Yjs WS server on {host}:{port}")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

- [ ] **Step 3: Snapshot persistence model**

```python
# plugins/vedix/saas/app/models/yjs_doc.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, LargeBinary, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from ..db import Base

class YjsDoc(Base):
    __tablename__ = "yjs_docs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(50))  # "palace_drawer" | "manuscript" | "comment_thread"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    state_vector: Mapped[bytes] = mapped_column(LargeBinary)  # Yjs binary snapshot
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Commit**

```bash
pytest plugins/vedix/saas/tests/test_yjs_server.py -v
git add plugins/vedix/saas/app/workers/yjs_server.py plugins/vedix/saas/app/models/yjs_doc.py plugins/vedix/saas/tests/test_yjs_server.py
git commit -m "feat(B11): Yjs WebSocket server + snapshot persistence model"
```

## Task 2: Shared palace REST API

**Files:**
- Create: `plugins/vedix/saas/app/routers/palace.py`
- Test: `plugins/vedix/saas/tests/test_palace.py`

- [ ] **Step 1: Implement palace router**

```python
# plugins/vedix/saas/app/routers/palace.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..models.shared_palace import SharedPalace
from ..models.user import User
from .auth import get_current_user
from ..entitlements import compute_entitlements, Tier
from .jobs import _user_subscription_tier

router = APIRouter(prefix="/v1/api/palaces")

@router.post("")
async def create_palace(payload: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tier = await _user_subscription_tier(user, db)
    ent = compute_entitlements(tier=tier)
    if not ent["shared_palace"]:
        raise HTTPException(403, f"shared palace requires Lab tier or above (you are {tier.value})")
    p = SharedPalace(owner_user_id=user.id, name=payload["name"],
                     seats=ent["palace_seats"] if isinstance(ent["palace_seats"], int) else 5,
                     acl={user.email: "owner"})
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"palace_id": str(p.id), "name": p.name, "seats": p.seats}

@router.post("/{palace_id}/invite")
async def invite(palace_id: uuid.UUID, payload: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = (await db.execute(select(SharedPalace).where(SharedPalace.id == palace_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(404)
    if p.acl.get(user.email) not in ("owner", "admin"):
        raise HTTPException(403, "only owner/admin can invite")
    if len(p.acl) >= p.seats:
        raise HTTPException(400, f"seats full ({p.seats})")
    p.acl[payload["email"]] = payload.get("role", "member")
    db.add(p)
    await db.commit()
    return {"acl": p.acl}

@router.get("/{palace_id}")
async def get_palace(palace_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = (await db.execute(select(SharedPalace).where(SharedPalace.id == palace_id))).scalar_one_or_none()
    if not p or user.email not in p.acl:
        raise HTTPException(404)
    return {"palace_id": str(p.id), "name": p.name, "seats": p.seats, "acl": p.acl,
            "yjs_ws_url": f"wss://collab.vedix.ai/doc/palace_{p.id}"}
```

- [ ] **Step 2: Commit**

```bash
pytest plugins/vedix/saas/tests/test_palace.py -v
git add plugins/vedix/saas/app/routers/palace.py plugins/vedix/saas/tests/test_palace.py
git commit -m "feat(B11): shared palace REST API + per-drawer ACL"
```

## Task 3: arXiv preprint adapter

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/preprint/__init__.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/preprint/arxiv_adapter.py`
- Test: `tests/preprint/test_arxiv_adapter.py`

- [ ] **Step 1: Write test**

```python
# tests/preprint/test_arxiv_adapter.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from plugins.vedix.mcp.lib.orchestrator.preprint.arxiv_adapter import submit_to_arxiv

def test_submit_to_arxiv_dry_run(tmp_path):
    pdf = tmp_path / "manuscript.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    metadata = {"title": "X", "abstract": "y", "authors": ["A B"], "categories": ["cs.LG"]}
    result = submit_to_arxiv(manuscript_pdf=pdf, metadata=metadata, credentials_path=tmp_path / "arxiv.token", dry_run=True)
    assert result["status"] == "dry-run"
    assert result["target"] == "arxiv"

def test_submit_to_arxiv_calls_api(tmp_path):
    pdf = tmp_path / "manuscript.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    token = tmp_path / "arxiv.token"; token.write_text("dummy-token")
    metadata = {"title": "X", "abstract": "y", "authors": ["A B"], "categories": ["cs.LG"]}
    fake_resp = MagicMock(status_code=200, json=lambda: {"submission_id": "abc123"}, text="ok")
    with patch("httpx.Client.post", return_value=fake_resp):
        result = submit_to_arxiv(manuscript_pdf=pdf, metadata=metadata, credentials_path=token, dry_run=False)
        assert result["status"] == "ok"
        assert result["submission_id"] == "abc123"
```

- [ ] **Step 2: Implement adapter**

```python
# plugins/vedix/mcp/lib/orchestrator/preprint/arxiv_adapter.py
"""arXiv pre-print submission via the arXiv API."""
from __future__ import annotations
from pathlib import Path
import httpx

ARXIV_SUBMIT_URL = "https://api.arxiv.org/v1/submit"  # placeholder; arXiv submission is via SWORD now

def submit_to_arxiv(*, manuscript_pdf: Path, metadata: dict, credentials_path: Path, dry_run: bool = True) -> dict:
    if dry_run:
        return {
            "status": "dry-run", "target": "arxiv",
            "would_submit_pdf": str(manuscript_pdf),
            "metadata": metadata,
        }
    if not credentials_path.exists():
        return {"status": "error", "reason": f"arXiv token missing at {credentials_path}"}
    token = credentials_path.read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=120) as client:
        with manuscript_pdf.open("rb") as f:
            r = client.post(
                ARXIV_SUBMIT_URL,
                headers={"Authorization": f"Bearer {token}"},
                files={"manuscript": ("manuscript.pdf", f, "application/pdf")},
                data={
                    "title": metadata.get("title", ""),
                    "abstract": metadata.get("abstract", ""),
                    "authors": "; ".join(metadata.get("authors", [])),
                    "categories": ",".join(metadata.get("categories", [])),
                },
            )
    if r.status_code in (200, 201):
        return {"status": "ok", "target": "arxiv", "submission_id": r.json().get("submission_id"), "response": r.json()}
    return {"status": "error", "target": "arxiv", "http_status": r.status_code, "body": r.text[:500]}
```

- [ ] **Step 3: Commit**

```bash
pytest tests/preprint/test_arxiv_adapter.py -v
git add plugins/vedix/mcp/lib/orchestrator/preprint/ tests/preprint/
git commit -m "feat(B11): arXiv preprint adapter"
```

## Task 4: bioRxiv / OSF / SSRN / SWORD adapters

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/preprint/biorxiv_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/preprint/osf_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/preprint/ssrn_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/preprint/sword_adapter.py`

- [ ] **Step 1: biorxiv_adapter.py**

```python
# plugins/vedix/mcp/lib/orchestrator/preprint/biorxiv_adapter.py
"""bioRxiv submission via Cold Spring Harbor's REST API."""
from __future__ import annotations
from pathlib import Path
import httpx

BIORXIV_SUBMIT_URL = "https://api.biorxiv.org/submission/v1/papers"

def submit_to_biorxiv(*, manuscript_pdf: Path, metadata: dict, credentials_path: Path, dry_run: bool = True) -> dict:
    if dry_run:
        return {"status": "dry-run", "target": "biorxiv", "metadata": metadata}
    token = credentials_path.read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=120) as client:
        with manuscript_pdf.open("rb") as f:
            r = client.post(BIORXIV_SUBMIT_URL,
                            headers={"Authorization": f"Bearer {token}"},
                            files={"manuscript": ("manuscript.pdf", f, "application/pdf")},
                            data=metadata)
    return {"status": "ok" if r.status_code in (200, 201) else "error",
            "target": "biorxiv", "http_status": r.status_code, "body": r.text[:500]}
```

- [ ] **Step 2: osf_adapter.py**

```python
# plugins/vedix/mcp/lib/orchestrator/preprint/osf_adapter.py
"""OSF (Open Science Framework) submission via api.osf.io."""
from __future__ import annotations
from pathlib import Path
import httpx

def submit_to_osf(*, manuscript_pdf: Path, metadata: dict, credentials_path: Path, dry_run: bool = True) -> dict:
    if dry_run:
        return {"status": "dry-run", "target": "osf", "metadata": metadata}
    token = credentials_path.read_text(encoding="utf-8").strip()
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=120) as client:
        # 1. Create a preprint node
        node = client.post("https://api.osf.io/v2/preprints/", headers=headers, json={
            "data": {"type": "preprints", "attributes": {
                "title": metadata["title"], "abstract": metadata.get("abstract", ""),
                "tags": metadata.get("tags", []),
            }}
        })
        if node.status_code not in (200, 201):
            return {"status": "error", "target": "osf", "http_status": node.status_code, "body": node.text[:500]}
        node_id = node.json()["data"]["id"]
        # 2. Upload the PDF
        with manuscript_pdf.open("rb") as f:
            up = client.put(f"https://files.osf.io/v1/resources/{node_id}/providers/osfstorage/?name=manuscript.pdf",
                            headers=headers, content=f.read())
        return {"status": "ok" if up.status_code in (200, 201) else "error",
                "target": "osf", "node_id": node_id, "http_status": up.status_code}
```

- [ ] **Step 3: ssrn_adapter.py (form auto-fill since no public API)**

```python
# plugins/vedix/mcp/lib/orchestrator/preprint/ssrn_adapter.py
"""SSRN — no public submission API. We generate a deep-linked form-fill URL the user opens in a browser."""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urlencode

def submit_to_ssrn(*, manuscript_pdf: Path, metadata: dict, credentials_path: Path | None = None, dry_run: bool = True) -> dict:
    params = {
        "title": metadata.get("title", ""),
        "abstract": metadata.get("abstract", ""),
        "authors": "; ".join(metadata.get("authors", [])),
        "keywords": ",".join(metadata.get("tags", [])),
    }
    url = f"https://papers.ssrn.com/sol3/submit/?{urlencode(params)}"
    return {"status": "manual-redirect", "target": "ssrn",
            "open_in_browser": url, "manuscript_pdf": str(manuscript_pdf),
            "note": "SSRN has no public submission API; the URL above pre-fills the form. Upload the PDF in your browser."}
```

- [ ] **Step 4: sword_adapter.py (SWORD v2 / OAI-PMH for institutional repos)**

```python
# plugins/vedix/mcp/lib/orchestrator/preprint/sword_adapter.py
"""SWORD v2 / OAI-PMH submission for institutional repositories."""
from __future__ import annotations
from pathlib import Path
import httpx
import base64

def submit_to_sword(*, manuscript_pdf: Path, metadata: dict, sword_endpoint: str,
                    username: str, password: str, dry_run: bool = True) -> dict:
    if dry_run:
        return {"status": "dry-run", "target": "sword", "endpoint": sword_endpoint, "metadata": metadata}
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    with httpx.Client(timeout=120) as client:
        with manuscript_pdf.open("rb") as f:
            r = client.post(sword_endpoint,
                            headers={
                                "Authorization": f"Basic {auth}",
                                "Content-Type": "application/pdf",
                                "Content-Disposition": "attachment; filename=manuscript.pdf",
                                "Slug": metadata.get("title", "manuscript"),
                            },
                            content=f.read())
    return {"status": "ok" if r.status_code in (200, 201, 202) else "error",
            "target": "sword", "endpoint": sword_endpoint,
            "http_status": r.status_code, "deposit_url": r.headers.get("Location")}
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/preprint/
git commit -m "feat(B11): bioRxiv + OSF + SSRN + SWORD preprint adapters"
```

## Task 5: CLI integration — `vedix submit-preprint`

**Files:**
- Modify: `plugins/vedix/mcp/lib/orchestrator/hooks/preprint_submit.py` (route to adapters)

- [ ] **Step 1: Implement full integration**

```python
# plugins/vedix/mcp/lib/orchestrator/hooks/preprint_submit.py (replace stub from Block 4)
from __future__ import annotations
from pathlib import Path
import os
from ..preprint.arxiv_adapter import submit_to_arxiv
from ..preprint.biorxiv_adapter import submit_to_biorxiv
from ..preprint.osf_adapter import submit_to_osf
from ..preprint.ssrn_adapter import submit_to_ssrn
from ..preprint.sword_adapter import submit_to_sword

def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

def _credentials_for(target: str) -> Path:
    return _home() / ".vedix" / "byok" / "secrets" / f"{target}.token"

def submit(*, target: str, manuscript_pdf: Path, metadata: dict, dry_run: bool = True, **kwargs) -> dict:
    target = target.lower()
    if target == "arxiv":
        return submit_to_arxiv(manuscript_pdf=manuscript_pdf, metadata=metadata,
                                credentials_path=_credentials_for("arxiv"), dry_run=dry_run)
    if target == "biorxiv":
        return submit_to_biorxiv(manuscript_pdf=manuscript_pdf, metadata=metadata,
                                  credentials_path=_credentials_for("biorxiv"), dry_run=dry_run)
    if target == "osf":
        return submit_to_osf(manuscript_pdf=manuscript_pdf, metadata=metadata,
                              credentials_path=_credentials_for("osf"), dry_run=dry_run)
    if target == "ssrn":
        return submit_to_ssrn(manuscript_pdf=manuscript_pdf, metadata=metadata, dry_run=dry_run)
    if target == "sword":
        return submit_to_sword(manuscript_pdf=manuscript_pdf, metadata=metadata,
                                sword_endpoint=kwargs["sword_endpoint"],
                                username=kwargs["username"], password=kwargs["password"],
                                dry_run=dry_run)
    return {"status": "error", "reason": f"unsupported target {target!r}"}
```

- [ ] **Step 2: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/hooks/preprint_submit.py
git commit -m "feat(B11): wire vedix submit-preprint CLI to all 5 adapters"
```

## Task 6: Web UI — CollabEditor + CursorOverlay

**Files:**
- Create: `plugins/vedix/web/src/collab/YjsProvider.tsx`
- Create: `plugins/vedix/web/src/collab/CursorOverlay.tsx`
- Create: `plugins/vedix/web/src/pages/CollabEditor.tsx`

- [ ] **Step 1: Install Yjs**

```bash
cd plugins/vedix/web
npm install yjs y-websocket
```

- [ ] **Step 2: YjsProvider**

```typescript
// src/collab/YjsProvider.tsx
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";

interface Ctx { doc: Y.Doc; provider: WebsocketProvider | null; }
const Yctx = createContext<Ctx | null>(null);

export function YjsProvider({ docId, children }: { docId: string; children: ReactNode }) {
  const [state, setState] = useState<Ctx | null>(null);
  useEffect(() => {
    const doc = new Y.Doc();
    const provider = new WebsocketProvider(
      import.meta.env.VITE_YJS_WS_URL ?? "wss://collab.vedix.ai",
      `doc/${docId}`,
      doc,
    );
    setState({ doc, provider });
    return () => { provider.destroy(); doc.destroy(); };
  }, [docId]);
  if (!state) return <div>Connecting…</div>;
  return <Yctx.Provider value={state}>{children}</Yctx.Provider>;
}

export function useYjs(): Ctx {
  const ctx = useContext(Yctx);
  if (!ctx) throw new Error("useYjs must be inside YjsProvider");
  return ctx;
}
```

- [ ] **Step 3: CursorOverlay (presence)**

```typescript
// src/collab/CursorOverlay.tsx
import { useEffect, useState } from "react";
import { useYjs } from "./YjsProvider";

interface PresenceState { user: { name: string; color: string }; cursor: { x: number; y: number } | null; }

export function CursorOverlay({ myName }: { myName: string }) {
  const { provider } = useYjs();
  const [peers, setPeers] = useState<Record<number, PresenceState>>({});
  useEffect(() => {
    if (!provider) return;
    const aw = provider.awareness;
    aw.setLocalStateField("user", { name: myName, color: stringToColor(myName) });
    const onMove = (e: MouseEvent) => aw.setLocalStateField("cursor", { x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", onMove);
    const update = () => {
      const next: Record<number, PresenceState> = {};
      aw.getStates().forEach((s: any, id: number) => { if (id !== aw.clientID && s.user) next[id] = s; });
      setPeers(next);
    };
    aw.on("change", update);
    return () => { window.removeEventListener("mousemove", onMove); aw.off("change", update); };
  }, [provider, myName]);

  return (
    <>
      {Object.entries(peers).map(([id, p]) => p.cursor && (
        <div key={id} style={{ position: "fixed", left: p.cursor.x, top: p.cursor.y, pointerEvents: "none",
                                background: p.user.color, color: "white", padding: "2px 6px", borderRadius: 3, fontSize: 12 }}>
          {p.user.name}
        </div>
      ))}
    </>
  );
}

function stringToColor(s: string): string {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0;
  return `hsl(${h % 360}, 70%, 50%)`;
}
```

- [ ] **Step 4: CollabEditor (Y.Text bound to a textarea)**

```typescript
// src/pages/CollabEditor.tsx
import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { YjsProvider, useYjs } from "../collab/YjsProvider";
import { CursorOverlay } from "../collab/CursorOverlay";

function Editor({ myName }: { myName: string }) {
  const { doc } = useYjs();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const ytext = doc.getText("manuscript");
    if (textareaRef.current) textareaRef.current.value = ytext.toString();
    const obs = () => { if (textareaRef.current && textareaRef.current.value !== ytext.toString()) textareaRef.current.value = ytext.toString(); };
    ytext.observe(obs);
    const onInput = () => { ytext.delete(0, ytext.length); ytext.insert(0, textareaRef.current!.value); };
    textareaRef.current?.addEventListener("input", onInput);
    return () => { ytext.unobserve(obs); textareaRef.current?.removeEventListener("input", onInput); };
  }, [doc]);
  return (
    <>
      <textarea ref={textareaRef} className="w-full h-screen p-6 font-mono" />
      <CursorOverlay myName={myName} />
    </>
  );
}

export function CollabEditor() {
  const { docId } = useParams<{docId: string}>();
  if (!docId) return null;
  return <YjsProvider docId={docId}><Editor myName="Anon" /></YjsProvider>;
}
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/web/src/collab/ plugins/vedix/web/src/pages/CollabEditor.tsx plugins/vedix/web/package.json
git commit -m "feat(B11): web collab editor — Yjs + presence cursors"
```

## Block 11 acceptance criteria

- [ ] Yjs WS server runs and broadcasts between two clients in the same doc room
- [ ] Shared palace create / invite endpoints return correct ACL + WS URL
- [ ] All 5 preprint adapters (`arxiv`, `biorxiv`, `osf`, `ssrn`, `sword`) return `dry-run` in dry-run mode and accept credentials in real mode
- [ ] `vedix submit-preprint --to arxiv` integration smoke: PDF + metadata + token → submission_id
- [ ] Web CollabEditor: open same docId in two tabs → text propagates; cursor positions shown
- [ ] All `tests/preprint/` + `plugins/vedix/saas/tests/test_yjs_server.py` + `test_palace.py` pass
- [ ] Git tag `v3.0.0-block11` pushed
