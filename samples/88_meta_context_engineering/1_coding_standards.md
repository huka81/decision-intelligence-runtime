# Coding Standards: Autonomous Flight Delay Refund System

**Document Type:** Compiler Instruction Set — Lexical & Semantic Rules  
**Scope:** All generated Python code for this sample  
**Enforcement:** Mandatory. Generated code MUST satisfy every rule below.

---

## 1. Language and Runtime

| Rule | Requirement |
|------|-------------|
| **LS-1** | Python 3.12 or higher. Use modern syntax (e.g., `type` statement for type aliases, pattern matching where appropriate). |
| **LS-2** | All modules MUST have `from __future__ import annotations` at the top to enable postponed evaluation of type hints. |
| **LS-3** | No `# type: ignore` without an explicit, justified comment. Prefer fixing the underlying type issue. |

---

## 2. Type Hints

| Rule | Requirement |
|------|-------------|
| **TH-1** | All function signatures MUST have complete type hints for parameters and return types. |
| **TH-2** | All module-level variables and class attributes MUST be typed. |
| **TH-3** | Use `typing` and `collections.abc` for generics. Prefer `list[str]` over `List[str]` (Python 3.9+ style). |
| **TH-4** | For optional values, use `X | None` or `Optional[X]` consistently. Never use untyped `None` returns. |
| **TH-5** | Use `Literal` for enumerated string values (e.g., `Literal["ACCEPT", "REJECT"]`). |
| **TH-6** | Use `TypedDict` or Pydantic for structured dictionaries. Raw `dict[str, Any]` is forbidden except for truly dynamic payloads, and must be justified. |

---

## 3. Pydantic

| Rule | Requirement |
|------|-------------|
| **PY-1** | Pydantic v2 only. Use `BaseModel` from `pydantic`. |
| **PY-2** | All data transfer objects (DTOs), policy proposals, and domain models MUST be Pydantic models. |
| **PY-3** | Use `Field()` for validation constraints (e.g., `Field(ge=0, le=100)`). Document fields with `description`. |
| **PY-4** | Use `model_config = ConfigDict(...)` for global settings (e.g., `frozen=True`, `extra="forbid"`). |
| **PY-5** | Prefer `model_validate()` and `model_dump()` over `parse_obj()` and `dict()` (Pydantic v2 API). |
| **PY-6** | Use `Field(serialization_alias=...)` for JSON schema compatibility when the Python name differs from the wire format. |

---

## 4. Global State and Implicit Magic

| Rule | Requirement |
|------|-------------|
| **GS-1** | **BAN** global mutable state. No module-level variables that are mutated at runtime (except configuration loaded once at startup). |
| **GS-2** | **BAN** implicit magic. No `__getattr__`-based dynamic dispatch, no hidden side effects in property access. |
| **GS-3** | **BAN** singletons unless explicitly required by the architecture (e.g., Agent Registry). If used, document the rationale. |
| **GS-4** | Dependencies MUST be injected explicitly (constructor injection or explicit parameters). No `import`-time side effects that alter global behavior. |
| **GS-5** | Configuration (API keys, URLs, feature flags) MUST be loaded from environment variables or a config object. Never hardcode secrets. |

---

## 5. Pure Functions vs. Side Effects

| Rule | Requirement |
|------|-------------|
| **PF-1** | **Pure functions** (validation, hashing, rule evaluation) MUST NOT perform I/O. They MUST be deterministic given the same inputs. |
| **PF-2** | **Side-effect functions** (API calls, database writes, ledger appends) MUST be clearly separated. Name them with verbs: `call_payout_api`, `append_to_ledger`. |
| **PF-3** | Pure validation logic MUST NOT depend on external services. It may depend on in-memory caches populated at startup. |
| **PF-4** | The boundary between User Space (reasoning, policy formation) and Kernel Space (validation, execution) MUST be explicit. No LLM calls inside the Proof Checker or Execution Engine. |
| **PF-5** | Functions that perform side effects MUST return a result type that indicates success or failure. Use `Result`-like types or raised exceptions with clear semantics. |

---

## 6. Logging

| Rule | Requirement |
|------|-------------|
| **LG-1** | **Structured JSON logging** only. Use `structlog` or `logging` with a JSON formatter. No unstructured `print()` for operational output. |
| **LG-2** | Every log entry MUST include: `dfid` (when in a decision flow), `event`, `timestamp`. |
| **LG-3** | Use log levels correctly: `DEBUG` for internal state, `INFO` for lifecycle events (e.g., "Policy accepted", "Ledger appended"), `WARNING` for recoverable issues, `ERROR` for failures. |
| **LG-4** | Sensitive data (passenger PII, payment details) MUST NOT appear in logs. Log hashes or redacted identifiers only. |
| **LG-5** | Log format MUST be parseable by standard log aggregators (e.g., `{"dfid": "...", "event": "...", "level": "info", "msg": "..."}`). |

---

## 7. Error Handling

| Rule | Requirement |
|------|-------------|
| **EH-1** | Define domain-specific exception classes. Do not rely on generic `Exception` for control flow. |
| **EH-2** | Validation failures MUST raise typed exceptions (e.g., `ValidationRejected`, `ProofVerificationFailed`) with structured `reason` and `details` fields. |
| **EH-3** | Catch only the exceptions you can handle. Let others propagate. Avoid bare `except:`. |
| **EH-4** | When re-raising, use `raise X from e` to preserve the chain. |

---

## 8. Testing and Determinism

| Rule | Requirement |
|------|-------------|
| **TE-1** | Pure functions MUST be unit-testable without mocks. Use deterministic inputs. |
| **TE-2** | Side-effect functions MUST be mockable. Inject dependencies (e.g., `PayoutClient`) so tests can substitute a stub. |
| **TE-3** | No `random` or `time.time()` in validation logic. Use injected clocks and deterministic IDs for tests. |
| **TE-4** | Test fixtures MUST be in a `fixtures/` directory or clearly namespaced. No production data in tests. |

---

## 9. Naming and Structure

| Rule | Requirement |
|------|-------------|
| **NM-1** | Use `snake_case` for functions, variables, modules. Use `PascalCase` for classes and Pydantic models. |
| **NM-2** | Constants: `UPPER_SNAKE_CASE`. |
| **NM-3** | Module names MUST reflect their responsibility. Avoid `utils.py` or `helpers.py` unless they contain truly generic utilities. |
| **NM-4** | Files in `src/` or package root. Entry point: `run.py` or `main.py`. |
| **NM-5** | One primary class or responsibility per module. Related types may be grouped (e.g., `models.py` for domain models). |

---

## 10. Security and Compliance

| Rule | Requirement |
|------|-------------|
| **SC-1** | No credentials in source code. Use environment variables or a secrets manager interface. |
| **SC-2** | Cryptographic operations (hashing, signing) MUST use `hashlib` or `cryptography`. No custom crypto. |
| **SC-3** | All external inputs (API responses, event payloads) MUST be validated before use. Treat them as untrusted. |
| **SC-4** | PII MUST be handled according to data minimization. Store only what is necessary for the decision and audit trail. |

---

## 11. DIR-Specific Constraints

| Rule | Requirement |
|------|-------------|
| **DIR-1** | **Proof Checker** MUST be deterministic. No LLM calls, no network I/O during verification. |
| **DIR-2** | **Decision Ledger** MUST be append-only. No updates or deletes. |
| **DIR-3** | **Idempotency Key** MUST follow `SHA256(DFID + Step_ID + Canonical_Params)`. `Attempt_Number` MUST NOT be in the key. |
| **DIR-4** | **DFID** MUST propagate through the entire pipeline. Every function that participates in a decision flow MUST accept and forward `dfid`. |
| **DIR-5** | **Agent (ROA)** MUST NOT hold API keys or database credentials. It submits proposals only. |
| **DIR-6** | **Kernel (DIR)** MUST validate every proposal before execution. No bypass. |

---

## Summary Checklist

Before considering the implementation complete, verify:

- [ ] Python 3.12+, `from __future__ import annotations`
- [ ] Full type hints, Pydantic v2 for all DTOs
- [ ] No global mutable state, no implicit magic
- [ ] Pure functions (validation) separated from side-effect functions (API, ledger)
- [ ] Structured JSON logging with `dfid` in decision-related logs
- [ ] Domain-specific exceptions, no bare `except`
- [ ] Proof Checker is deterministic; no LLM in Kernel Space
- [ ] DFID propagation, Idempotency Key formula, append-only Ledger
