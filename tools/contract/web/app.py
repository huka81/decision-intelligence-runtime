"""FastAPI application for Contract Studio."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..bootstrap_rules import BootstrapValidationError, validate_bootstrap
from ..db.store import ContractStudioStore
from ..env import load_contract_env
from ..integrity import verify_contract_yaml
from ..governance.context import build_governance_context
from ..governance.models import GovernanceAnalysis
from ..llm_interview import (
    empty_draft_contract,
    mock_contract_llm_strategy,
    process_chat_turn,
    validate_contract_soft,
)
from ..render import render_registry_yaml, write_emitted_files
from ..schema import CanonicalContract
from ..settings import (
    DebugLoggingLLM,
    StudioSettings,
    configure_studio_logging,
    load_studio_settings,
)

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_VERSIONED_ASSETS = ("app.js", "styles.css")


def _asset_version() -> str:
    """
    Fingerprint front-end assets so a browser cannot serve a stale bundle.

    Mismatched HTML and JS break the UI silently (missing element ids), so the
    version is derived from file mtimes and injected into the asset URLs.
    """
    stamps = []
    for name in _VERSIONED_ASSETS:
        path = _STATIC_DIR / name
        stamps.append(str(path.stat().st_mtime_ns) if path.is_file() else "0")
    return hashlib.sha256("|".join(stamps).encode("utf-8")).hexdigest()[:12]


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


class SaveContractRequest(BaseModel):
    """Hand-edited canonical YAML submitted from the Contract Studio editor."""

    yaml: str


def _db_path(settings: Optional[StudioSettings] = None) -> Path:
    resolved = settings or load_studio_settings()
    return resolved.db_path


def _has_gemini_key() -> bool:
    return bool(
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )


def _build_llm(settings: Optional[StudioSettings] = None):
    """Resolve LLM for Contract Studio from config.yaml (+ API key from .env).

    Priority:
    1. ``studio.use_mock_llm`` / ``USE_MOCK_LLM`` → mock
    2. ``studio.llm_provider`` / ``CONTRACT_STUDIO_LLM`` → that provider
    3. Gemini when ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` is present
    4. Ollama when reachable
    5. Mock fallback (with warning)
    """
    from samples.shared.bootstrap import build_llm_from_config, configured_live_llm_is_reachable
    from samples.shared.llm.clients import check_ollama

    settings = settings or load_studio_settings()
    llm_defaults: Dict[str, Any] = dict(settings.llm_defaults)
    override = (settings.llm_provider or "").strip().lower()
    use_mock = settings.use_mock_llm

    if use_mock or override == "mock":
        llm_defaults["provider"] = "mock"
    elif override in ("gemini", "ollama"):
        llm_defaults["provider"] = override
        if override == "gemini":
            llm_defaults["model"] = (
                llm_defaults.get("gemini_model") or "gemini-flash-lite-latest"
            )
    elif _has_gemini_key():
        llm_defaults["provider"] = "gemini"
        llm_defaults["model"] = (
            llm_defaults.get("gemini_model") or "gemini-flash-lite-latest"
        )
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
                "Set GEMINI_API_KEY in tools/contract/.env or start Ollama, "
                "or set studio.use_mock_llm: true in config.yaml."
            )
            llm_defaults["provider"] = "mock"

    config: Dict[str, Any] = {"llm_defaults": llm_defaults}

    if llm_defaults.get("provider") in ("gemini", "ollama") and not configured_live_llm_is_reachable(
        config
    ):
        logger.warning(
            "Contract Studio: configured provider '%s' is not usable — falling back to mock.",
            llm_defaults.get("provider"),
        )
        llm_defaults["provider"] = "mock"
        config["llm_defaults"] = llm_defaults

    logger.info(
        "Contract Studio LLM: provider=%s model=%s debug=%s config=%s",
        llm_defaults.get("provider"),
        llm_defaults.get("model"),
        settings.debug,
        settings.config_path,
    )

    inner = build_llm_from_config(
        config,
        mock_llm_strategy=mock_contract_llm_strategy,
    )
    return DebugLoggingLLM(inner, enabled=settings.debug)


def create_app(settings: Optional[StudioSettings] = None) -> FastAPI:
    settings = settings or load_studio_settings()
    configure_studio_logging(debug=settings.debug)

    app = FastAPI(title="Contract Studio", version="0.1.0")
    store = ContractStudioStore(_db_path(settings))
    llm = _build_llm(settings)
    llm_label = (
        "mock"
        if settings.use_mock_llm or (settings.llm_provider or "") == "mock"
        else (settings.llm_provider or "auto")
    )

    def _governance_payload(session_id: str, revision_id: Optional[str]) -> Dict[str, Any]:
        if not revision_id:
            return {
                "governance_analysis": None,
                "validation_warnings": [],
                "governance_report": None,
            }
        assessment = store.get_governance_assessment(revision_id)
        if assessment is None:
            return {
                "governance_analysis": None,
                "validation_warnings": [],
                "governance_report": None,
            }
        analysis = None
        if assessment.analysis_json:
            try:
                analysis = json.loads(assessment.analysis_json)
            except json.JSONDecodeError:
                analysis = None
        report = None
        try:
            report = json.loads(assessment.report_json)
        except json.JSONDecodeError:
            report = None
        return {
            "governance_analysis": analysis,
            "validation_warnings": store.assessment_warnings(assessment),
            "governance_report": report,
        }

    def _session_payload(session_id: str) -> Dict[str, Any]:
        session = store.get_session(session_id)
        messages = store.list_messages(session_id)
        revision = store.get_current_revision(session_id)
        contract_yaml = revision.contract_yaml if revision else ""
        validation_ok = revision.validation_ok if revision else False
        errors = store.revision_errors(revision) if revision else []
        gov = _governance_payload(session_id, revision.id if revision else None)
        snapshot = store.get_governance_snapshot(session_id)
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
            "validation_warnings": gov["validation_warnings"],
            "governance_analysis": gov["governance_analysis"],
            "governance_report": gov["governance_report"],
            "governance_context_hash": snapshot.context_hash if snapshot else None,
            "revision_no": revision.revision_no if revision else 0,
        }

    @app.get("/")
    async def index() -> HTMLResponse:
        html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__ASSET_VERSION__", _asset_version())
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.post("/api/sessions")
    async def create_session(payload: CreateSessionRequest) -> Dict[str, Any]:
        session = store.create_session(
            title=payload.title,
            preset=payload.preset,
            llm_provider=llm_label,
        )
        welcome = (
            "Welcome to Contract Studio. Describe your agent: domain, mission, "
            "owner email, irreversible limits, and allowed actions."
        )
        store.add_message(session.id, "system", welcome)
        store.add_message(session.id, "assistant", welcome)

        draft = empty_draft_contract(payload.preset)
        context_snapshot = build_governance_context(preset=payload.preset, role=draft["subject"]["role"])
        store.ensure_governance_snapshot(session.id, context_snapshot)

        contract, ok, errors, warnings = validate_contract_soft(draft, preset=payload.preset)
        yaml_text = "# Draft contract — describe your agent in chat\n"
        if contract:
            yaml_text = render_registry_yaml(contract)
        store.add_revision(
            session.id,
            contract_json=json.dumps(draft),
            contract_yaml=yaml_text,
            validation_ok=ok,
            validation_errors=errors,
            change_summary="Initial empty draft",
            governance_assessment={
                "analysis": None,
                "report": {"blocking_ok": ok, "warnings": warnings},
                "warnings": warnings,
            },
        )
        store.update_session(
            session.id,
            agent_id=draft.get("subject", {}).get("agent_id"),
        )
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

        snapshot_row = store.get_governance_snapshot(session_id)
        context_snapshot = None
        prior_analysis = None
        prior_warnings: List[str] = []
        if snapshot_row:
            context_snapshot = json.loads(snapshot_row.context_json)
        if revision:
            assessment = store.get_governance_assessment(revision.id)
            if assessment and assessment.analysis_json:
                try:
                    prior_analysis = GovernanceAnalysis.model_validate(
                        json.loads(assessment.analysis_json)
                    )
                except Exception:
                    prior_analysis = None
            if assessment:
                prior_warnings = store.assessment_warnings(assessment)

        try:
            turn = process_chat_turn(
                llm,
                current_contract=current,
                chat_history=history,
                user_message=user_msg,
                preset=session.preset,
                context_snapshot=context_snapshot,
                prior_warnings=prior_warnings,
                prior_analysis=prior_analysis,
            )
        except Exception as exc:
            logger.exception("LLM chat failed")
            raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc

        assistant_msg = store.add_message(session_id, "assistant", turn.assistant_reply)
        assessment_payload = {
            "analysis": turn.governance_analysis.model_dump() if turn.governance_analysis else None,
            "report": turn.validation_report.model_dump() if turn.validation_report else {},
            "warnings": turn.warnings,
            "llm_response": turn.llm_response.model_dump() if turn.llm_response else None,
        }
        store.add_revision(
            session_id,
            contract_json=json.dumps(turn.merged_contract),
            contract_yaml=turn.contract_yaml,
            validation_ok=turn.validation_ok,
            validation_errors=turn.blocking_errors,
            source_message_id=assistant_msg.id,
            change_summary=turn.change_summary,
            governance_assessment=assessment_payload,
        )
        status = "ready" if turn.validation_ok else "drafting"
        new_agent_id = turn.merged_contract.get("subject", {}).get("agent_id")
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
            "assistant_reply": turn.assistant_reply,
            "contract_yaml": turn.contract_yaml,
            "validation_ok": turn.validation_ok,
            "validation_errors": turn.blocking_errors,
            "validation_warnings": turn.warnings,
            "governance_analysis": assessment_payload["analysis"],
            "status": status,
            "change_summary": turn.change_summary,
        }

    @app.put("/api/sessions/{session_id}/contract")
    async def save_contract(
        session_id: str, payload: SaveContractRequest
    ) -> Dict[str, Any]:
        """
        Persist a hand-edited contract and validate it in the same request.

        A revision is created only when the YAML parses against the canonical
        schema; Bootstrap and governance findings are reported but do not
        prevent saving, mirroring the chat flow.
        """
        try:
            session = store.get_session(session_id)
            revision = store.get_current_revision(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        raw_yaml = payload.yaml
        if not raw_yaml.strip():
            raise HTTPException(status_code=400, detail="yaml must not be empty")

        prior_analysis: Optional[GovernanceAnalysis] = None
        prior_analysis_json: Optional[Dict[str, Any]] = None
        if revision is not None:
            assessment = store.get_governance_assessment(revision.id)
            if assessment and assessment.analysis_json:
                try:
                    prior_analysis_json = json.loads(assessment.analysis_json)
                    prior_analysis = GovernanceAnalysis.model_validate(
                        prior_analysis_json
                    )
                except Exception:
                    prior_analysis = None
                    prior_analysis_json = None

        def _rejected(errors: List[str]) -> Dict[str, Any]:
            return {
                "saved": False,
                "contract_yaml": raw_yaml,
                "validation_ok": False,
                "validation_errors": errors,
                "validation_warnings": [],
                "governance_analysis": prior_analysis_json,
                "status": session.status,
                "change_summary": None,
            }

        try:
            parsed = yaml.safe_load(raw_yaml)
        except yaml.YAMLError as exc:
            return _rejected([f"yaml: {exc}"])

        if not isinstance(parsed, dict):
            return _rejected(["yaml: contract must be a YAML mapping"])

        contract, validation_ok, errors, warnings = validate_contract_soft(
            parsed,
            preset=session.preset,
            governance_analysis=prior_analysis,
        )
        if contract is None:
            return _rejected(errors)

        contract_dict = contract.model_dump(exclude_none=True)
        canonical_yaml = render_registry_yaml(contract)
        new_revision = store.add_revision(
            session_id,
            contract_json=json.dumps(contract_dict),
            contract_yaml=canonical_yaml,
            validation_ok=validation_ok,
            validation_errors=errors,
            change_summary="Manual YAML edit",
            governance_assessment={
                "analysis": prior_analysis_json,
                "report": {"blocking_ok": validation_ok, "warnings": warnings},
                "warnings": warnings,
            },
        )
        status = "ready" if validation_ok else "drafting"
        store.update_session(
            session_id,
            agent_id=contract_dict.get("subject", {}).get("agent_id"),
            status=status,
        )
        store.add_message(
            session_id,
            "system",
            f"Contract edited manually (revision {new_revision.revision_no}).",
        )

        return {
            "saved": True,
            "contract_yaml": canonical_yaml,
            "validation_ok": validation_ok,
            "validation_errors": errors,
            "validation_warnings": warnings,
            "governance_analysis": prior_analysis_json,
            "status": status,
            "change_summary": "Manual YAML edit",
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
        if revision is not None:
            assessment = store.get_governance_assessment(revision.id)
            if assessment:
                result["validation_warnings"] = store.assessment_warnings(assessment)
                try:
                    result["governance_report"] = json.loads(assessment.report_json)
                except json.JSONDecodeError:
                    result["governance_report"] = None
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


load_contract_env()
app = create_app()
