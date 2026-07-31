"""FastAPI application for Contract Studio."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..bootstrap_rules import BootstrapValidationError, validate_bootstrap
from ..db.store import ContractStudioStore
from ..integrity import verify_contract_yaml
from ..llm_interview import (
    empty_draft_contract,
    mock_contract_llm_strategy,
    process_chat_turn,
    validate_contract_soft,
)
from ..render import write_emitted_files
from ..schema import CanonicalContract

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_LLM_CONFIG = Path(__file__).parent / "llm_config.yaml"
_REPO_ROOT = Path(__file__).resolve().parents[3]


class CreateSessionRequest(BaseModel):
    title: str = "New contract"
    preset: Optional[str] = None


class ChatRequest(BaseModel):
    message: str


class ExportRequest(BaseModel):
    emit: Literal["registry", "sample", "both"] = "both"
    out: Optional[str] = None


class ValidateRequest(BaseModel):
    """Optional YAML body; when omitted, validates the current revision YAML."""

    yaml: Optional[str] = None


class RenameSessionRequest(BaseModel):
    title: str


def _db_path() -> Path:
    env = os.environ.get("CONTRACT_STUDIO_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "contract_studio.db"


def _has_gemini_key() -> bool:
    return bool(
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )


def _build_llm():
    """Resolve LLM for Contract Studio.

    Priority:
    1. ``USE_MOCK_LLM=1`` → mock
    2. ``CONTRACT_STUDIO_LLM`` env (gemini|ollama|mock) if set
    3. Gemini when ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` is present
    4. Ollama when reachable
    5. Mock fallback (with warning)
    """
    from samples.shared.bootstrap import build_llm_from_config, configured_live_llm_is_reachable
    from samples.shared.llm.clients import check_ollama

    config: Dict[str, Any] = {}
    if _LLM_CONFIG.is_file():
        with open(_LLM_CONFIG, encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}

    llm_defaults: Dict[str, Any] = dict(config.get("llm_defaults") or {})
    override = os.environ.get("CONTRACT_STUDIO_LLM", "").strip().lower()
    use_mock = os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")

    if use_mock or override == "mock":
        llm_defaults["provider"] = "mock"
    elif override in ("gemini", "ollama"):
        llm_defaults["provider"] = override
        if override == "gemini":
            llm_defaults.setdefault("model", "gemini-flash-lite-latest")
    elif _has_gemini_key():
        # Prefer Gemini when a cloud API key is available (Ollama often offline locally).
        llm_defaults["provider"] = "gemini"
        llm_defaults["model"] = llm_defaults.get("gemini_model") or "gemini-flash-lite-latest"
        logger.info("Contract Studio: using Gemini (API key detected).")
    else:
        base_url = llm_defaults.get("base_url", "http://localhost:11434")
        model = llm_defaults.get("model", "gemma3:4b")
        if check_ollama(base_url, model):
            llm_defaults["provider"] = "ollama"
            logger.info("Contract Studio: using Ollama (%s).", model)
        else:
            logger.warning(
                "Contract Studio: Ollama unreachable and no GEMINI_API_KEY — using mock LLM. "
                "Set GEMINI_API_KEY or start Ollama, or USE_MOCK_LLM=1 to silence this."
            )
            llm_defaults["provider"] = "mock"

    config["llm_defaults"] = llm_defaults

    # If explicit gemini/ollama still unreachable, fall back to mock rather than crash on first chat.
    if llm_defaults.get("provider") in ("gemini", "ollama") and not configured_live_llm_is_reachable(
        config
    ):
        logger.warning(
            "Contract Studio: configured provider '%s' is not usable — falling back to mock.",
            llm_defaults.get("provider"),
        )
        llm_defaults["provider"] = "mock"
        config["llm_defaults"] = llm_defaults

    return build_llm_from_config(
        config,
        mock_llm_strategy=mock_contract_llm_strategy,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Contract Studio", version="0.1.0")
    store = ContractStudioStore(_db_path())
    llm = _build_llm()

    def _session_payload(session_id: str) -> Dict[str, Any]:
        session = store.get_session(session_id)
        messages = store.list_messages(session_id)
        revision = store.get_current_revision(session_id)
        contract_yaml = revision.contract_yaml if revision else ""
        validation_ok = revision.validation_ok if revision else False
        errors = store.revision_errors(revision) if revision else []
        return {
            "session": {
                "id": session.id,
                "agent_id": session.agent_id,
                "title": session.title,
                "preset": session.preset,
                "status": session.status,
                "current_revision_id": session.current_revision_id,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            },
            "messages": [
                {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
                for m in messages
            ],
            "contract_yaml": contract_yaml,
            "validation_ok": validation_ok,
            "validation_errors": errors,
            "revision_no": revision.revision_no if revision else 0,
        }

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.post("/api/sessions")
    async def create_session(payload: CreateSessionRequest) -> Dict[str, Any]:
        session = store.create_session(
            title=payload.title,
            preset=payload.preset,
            llm_provider=os.environ.get("USE_MOCK_LLM", "live"),
        )
        welcome = (
            "Welcome to Contract Studio. Describe your agent: domain, mission, "
            "owner email, irreversible limits, and allowed actions."
        )
        store.add_message(session.id, "system", welcome)
        store.add_message(session.id, "assistant", welcome)

        draft = empty_draft_contract(payload.preset)
        contract, ok, errors = validate_contract_soft(draft, preset=payload.preset)
        yaml_text = "# Draft contract — describe your agent in chat\n"
        if contract:
            from ..render import render_registry_yaml

            yaml_text = render_registry_yaml(contract)
        store.add_revision(
            session.id,
            contract_json=json.dumps(draft),
            contract_yaml=yaml_text,
            validation_ok=ok,
            validation_errors=errors,
            change_summary="Initial empty draft",
        )
        store.update_session(session.id, agent_id=draft.get("agent_id"))
        return _session_payload(session.id)

    @app.get("/api/sessions")
    async def list_sessions() -> Dict[str, Any]:
        sessions = store.list_sessions()
        return {
            "sessions": [
                {
                    "id": s.id,
                    "title": s.title,
                    "preset": s.preset,
                    "status": s.status,
                    "agent_id": s.agent_id,
                    "updated_at": s.updated_at,
                }
                for s in sessions
            ]
        }

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> Dict[str, Any]:
        try:
            return _session_payload(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/api/sessions/{session_id}")
    async def rename_session(session_id: str, payload: RenameSessionRequest) -> Dict[str, Any]:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="title must not be empty")
        try:
            store.update_session(session_id, title=title)
            return _session_payload(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> Dict[str, Any]:
        try:
            store.delete_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"deleted": True, "id": session_id}

    @app.get("/api/sessions/{session_id}/revisions")
    async def list_revisions(session_id: str) -> Dict[str, Any]:
        try:
            revisions = store.list_revisions(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "revisions": [
                {
                    "id": r.id,
                    "revision_no": r.revision_no,
                    "validation_ok": r.validation_ok,
                    "validation_errors": store.revision_errors(r),
                    "change_summary": r.change_summary,
                    "created_at": r.created_at,
                }
                for r in revisions
            ]
        }

    @app.post("/api/sessions/{session_id}/chat")
    async def chat(session_id: str, payload: ChatRequest) -> Dict[str, Any]:
        try:
            session = store.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        user_msg = payload.message.strip()
        if not user_msg:
            raise HTTPException(status_code=400, detail="message must not be empty")

        store.add_message(session_id, "user", user_msg)
        messages = store.list_messages(session_id)
        history = [(m.role, m.content) for m in messages if m.role in ("user", "assistant")]

        revision = store.get_current_revision(session_id)
        current = json.loads(revision.contract_json) if revision else empty_draft_contract(session.preset)

        try:
            reply, merged, yaml_text, validation_ok, errors, summary = process_chat_turn(
                llm,
                current_contract=current,
                chat_history=history,
                user_message=user_msg,
                preset=session.preset,
            )
        except Exception as exc:
            logger.exception("LLM chat failed")
            raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc

        assistant_msg = store.add_message(session_id, "assistant", reply)
        store.add_revision(
            session_id,
            contract_json=json.dumps(merged),
            contract_yaml=yaml_text,
            validation_ok=validation_ok,
            validation_errors=errors,
            source_message_id=assistant_msg.id,
            change_summary=summary,
        )
        status = "ready" if validation_ok else "drafting"
        new_agent_id = merged.get("agent_id")
        title_update = None
        if (
            new_agent_id
            and new_agent_id != "draft_agent"
            and session.title.startswith("Contract (")
        ):
            title_update = new_agent_id
        store.update_session(
            session_id,
            agent_id=new_agent_id,
            title=title_update,
            status=status,
        )

        return {
            "assistant_reply": reply,
            "contract_yaml": yaml_text,
            "validation_ok": validation_ok,
            "validation_errors": errors,
            "status": status,
            "change_summary": summary,
        }

    @app.post("/api/sessions/{session_id}/validate")
    async def validate_session(session_id: str, payload: ValidateRequest) -> Dict[str, Any]:
        """Parse YAML and confirm schema + Bootstrap integrity."""
        try:
            session = store.get_session(session_id)
            revision = store.get_current_revision(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        yaml_text = (payload.yaml or "").strip()
        if not yaml_text:
            if revision is None or not revision.contract_yaml.strip():
                raise HTTPException(status_code=400, detail="No YAML to validate")
            yaml_text = revision.contract_yaml

        expected = None
        if revision is not None:
            try:
                expected = json.loads(revision.contract_json)
            except json.JSONDecodeError:
                expected = None

        result = verify_contract_yaml(
            yaml_text,
            preset=session.preset,
            expected_json=expected,
        )

        if result["integrity_ok"] and session.status == "drafting":
            store.update_session(session_id, status="ready")
            result["status"] = "ready"
        else:
            result["status"] = session.status if result["integrity_ok"] else "drafting"

        result["validation_ok"] = result["integrity_ok"]
        result["validation_errors"] = result.get("errors") or []
        return result

    @app.post("/api/sessions/{session_id}/export")
    async def export_session(session_id: str, payload: ExportRequest) -> Dict[str, Any]:
        try:
            session = store.get_session(session_id)
            revision = store.get_current_revision(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if revision is None:
            raise HTTPException(status_code=400, detail="No contract revision to export")

        if not revision.validation_ok:
            errors = store.revision_errors(revision)
            raise HTTPException(
                status_code=400,
                detail={"message": "Contract fails Bootstrap validation", "errors": errors},
            )

        contract = CanonicalContract.model_validate(json.loads(revision.contract_json))
        try:
            validate_bootstrap(contract, preset=session.preset)
        except BootstrapValidationError as exc:
            raise HTTPException(status_code=400, detail={"errors": exc.errors}) from exc

        out_dir = Path(payload.out) if payload.out else _REPO_ROOT / "contracts"
        written = write_emitted_files(contract, emit=payload.emit, out_dir=out_dir)  # type: ignore[arg-type]
        paths = [str(p) for p in written.values()]
        store.add_export(session_id, revision.id, payload.emit, paths)

        return {"exported": True, "paths": paths, "emit": payload.emit}

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    return app


app = create_app()
