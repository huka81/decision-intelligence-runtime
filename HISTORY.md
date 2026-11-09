# Project history

Chronology of **what changed for readers and operators** of the Decision Intelligence Runtime: from the first publication of the ROA/DIR narrative through runnable governance scenarios, a hardened decision kernel, and a public documentation site. Technical file moves or line counts are omitted when they do not change the business story.

---

## 2025-12-11 — Project start

- The repository opens as a home for the **Responsibility-Oriented Agents (ROA)** manifesto: a clear statement of how agent work is scoped, delegated, and owned when decisions have operational consequences.

---

## 2026-01 — Decision Intelligence pattern, ready for serious readers

- The **Decision Intelligence Runtime (DIR)** pattern is spelled out alongside ROA so teams can see how decision flows, contracts, and execution boundaries fit together in production-shaped systems.
- Architecture prose is tightened for **clarity, consistency, and implementability** (definitions, cross-references, glossary, and references), with diagrams that leadership and engineering can share without re-drawing the stack on a whiteboard each time.
- A **production-readiness** pass signals intent: this is not only conceptual writing; it is meant to inform how real services are governed.

---

## 2026-01-26 — Operating topologies

- **Topologies** are introduced as named ways the same ROA/DIR ideas show up in live operations (different balances of autonomy, ledgering, and policy enforcement).
- **Topology C** foregrounds a **decision ledger with pre-commit intent (DL+PCI)** as the pattern where financial and compliance-grade controls are first-class, not bolted on after the fact.

---

## 2026-02-03 to 2026-02-05 — First worked scenarios

- The project ships **initial worked examples** so abstract topologies can be traced to concrete flows (who decides, what is logged, what can be blocked).
- Public **status and orientation** in the README help newcomers understand maturity and where to start.

---

## 2026-02-14 — Onboarding narrative

- A dedicated **introduction to DIR** lowers the barrier for stakeholders who need the “why” before the “how”.
- **Figures and graphs** support executive and architecture conversations without requiring a live demo on day one.

---

## 2026-02-16 — Delegation in the real AI conversation

- The work is **mapped to the Intelligent AI Delegation framing** so buyers and architects can place DIR next to mainstream agent research without conflating autonomy with authority.
- **Topology B vs C** examples make the trade-off tangible: where agents may move fast versus where the ledger and intent gates must dominate.
- **EOAM-style live simulation** material is refined so time-to-insight for “what breaks under load or ambiguity” is shorter in workshops.

---

## 2026-02-18 — Business-shaped examples per topology

- Examples are reframed around **recognisable business domains** so risk, compliance, and product leaders can argue from scenarios, not only from principles.
- The **sample catalogue** is organised so each scenario states intent, boundaries, and outcomes in one place (discoverability for audits and sales engineering).

---

## 2026-02-19 to 2026-02-20 — Trading narrative, wrappers, and “context as code”

- The **trading / market-style simulation** gains **decision-grade reporting** leadership can skim after a run (not only console output for developers).
- A **LangChain-oriented ROA wrapper** shows how popular agent frameworks can still run under **mission and policy injection** from DIR, instead of replacing governance.
- **Meta-context engineering** illustrates how context is curated as a managed asset, not an accidental chat transcript.
- The **Context as Code** article (with a portable PDF) positions compile-time and review-time context as a first-class governance lever.
- **Scope and boundary clarifications** in ROA/DIR reduce mis-selling: where learning and autonomy sit, what the OS analogy does and does not claim, and why **model confidence must not imply execution authority**.

---

## 2026-02-24 to 2026-02-28 — Repeatable evidence and fraud-shaped controls

- The trading-style scenario can **persist results** so comparisons across runs support **internal risk reviews** and stakeholder walkthroughs without rerunning everything from scratch.
- **Fraud-gate style** material is stabilised so “stop / escalate / release” paths read consistently in data views teams already use.
- ROA is positioned explicitly as a **governance wrapper around generative frameworks**, clarifying procurement and architecture conversations with LLM-centric vendors.

---

## 2026-03-02 — Richer partner and vertical stories

- **Finance, fraud, and agent-framework wrapper** samples expand so prospects see **industry-relevant** paths, not only generic chatbots.
- Topology documentation is aligned with that wave so **named topologies still match what the samples exhibit**.

---

## 2026-03-03 — Decision kernel that matches the narrative

- The runtime gains explicit primitives for **just-in-time compilation of decision context, ledgering, pre-commit intent, arbitration, and wake-ups**, so demonstrations line up with the **safety and audit story** told in the long-form architecture.
- **LLM access** is treated as a **replaceable integration** (local or vendor) rather than a hidden dependency inside samples.

---

## 2026-03-04 — Trust, contribution, and a five-minute path to value

- **Automated tests** back critical behaviors: registry rules, decision identity and TTL, escalation, retried intents, resource contention, and saga-style flows. That supports **change confidence** as the kernel grows.
- **Contributor norms, licensing, and packaging** appear so organisations can adopt or fork with clear legal and process footing.
- **Quick start** material targets **time-to-first governed decision** for a new engineer or architect on a laptop.

---

## 2026-03-09 to 2026-03-13 — Compact spec for builders, smoother LLM onboarding

- A **short “DIR minified” specification** gives implementers a dense contract-and-telemetry view without rereading the entire essay corpus.
- **Meta-context** sample guidance is tightened for teams that already run context pipelines.
- **Quick start** is improved so runs can switch between **mock and live LLM** behavior with **operationally readable logging**, reducing false starts in pilots.

---

## 2026-03-20 to 2026-03-21 — Underwriting under adversarial pressure, plus public Q&A

- The **insurance underwriting** scenario is rebuilt end-to-end: policy gates, model-assisted judgment, and **reporting suitable for a control discussion**, not only a developer trace.
- A **prompt-injection style storyline** makes explicit how **agent-facing attacks** surface in underwriting workflows and how DIR-style gates respond.
- An **FAQ** answers recurring buyer and practitioner questions so the same objections are not rehashed privately in every meeting.

---

## 2026-03-25 — Sharper contracts in the minified spec

- **Contracts, policy proposals, structured decision telemetry, and execution intent** language is reconciled so security and compliance reviewers see **one coherent story** in the compact specification.

---

## 2026-04-01 — Reference drift scenarios (optimization, refunds, marketing efficiency)

- **Retention and discount programs**: reference material for **reward hacking and optimisation drift** when short-term metrics diverge from durable customer value.
- **Refund and support operations**: reference material for **semantic and policy drift** where agents stretch business rules unless compliance monitors and caps are explicit.
- **Paid acquisition and bidding**: reference material where **environmental shifts** (for example cost per click versus customer value) create silent margin erosion unless ROI-style monitors and bidding constraints stay aligned.
- Narrative and experiment descriptions are aligned so **risk, product, and data leaders** can compare the three failure families side by side.

---

## 2026-04-02 — Governance as a first-class chapter

- Documentation adds an explicit **governance** block: how policies, ownership, and operating boundaries are expected to work when agents touch customer-facing and money-moving decisions.

---

## 2026-04-12 — Public documentation site

- A **MkDocs-powered site** publishes the architecture, samples, and supporting pages so **external audiences** (customers, regulators’ technical contacts, partners) can browse a stable URL.
- **GitHub Pages** deployment makes updates part of the normal delivery rhythm instead of a manual export.
- **Diagrams render on the site** so architecture reviews can point to the same figures online and in decks.
- **Samples are surfaced in navigation** so evaluation teams can jump from concept to runnable scenario quickly.

---

## 2026-04-12 to 2026-04-16 — Runtime becomes an installable library

- The runtime is **renamed and repackaged as `dir_core`**, with **storage abstracted behind swappable backends** (in-memory, SQLite, PostgreSQL), so adopters can plug DIR into their own persistence instead of inheriting a fixed one.
- The code is **prepared for a hexagonal (ports-and-adapters) layout** and gains **explicit data types** for decision artefacts, making contracts between kernel, agents, and integrations easier to review and test.

---

## 2026-04-17 — Full sample catalogue, one simple entry point

- Runnable scenarios are rebuilt on top of the library: **finance trading, fraud gate, insurance underwriting, LangChain and CrewAI wrappers**, and the three **drift** references (discount optimisation, semantic refund, environmental bidding).
- A **00 Quick Start** sample and a **facade over the kernel** give new teams a short path to a first governed decision without wiring every component by hand.
- A **package README** describes what `dir_core` offers and how to consume it.

---

## 2026-04-21 to 2026-04-23 — Contract lifecycle, custom persistence, first release

- **Governance documentation** adds a **contract lifecycle** and a **graduated circuit breaker**, so operators see how rules are introduced, tightened, and halted when behaviour degrades.
- A **custom PostgreSQL repository sample (08)** shows how to bring your own storage; topology samples **09, 10, and 11** are aligned with the new runtime.
- A **basic Ollama test** covers the local-LLM path.
- **`dir-core` v0.1.0 is published**, the first versioned release that teams can pin in their own environments.
- Documentation-site publishing is **fixed and re-pointed** (workflow trigger, `mkdocstrings` dependency, MkDocs configuration), so the public site reliably reflects the release.

---

## 2026-05 — Canonical data model and v0.2.0

- The **canonical data model** is refined and documented in the database schema reference, and the **decision lifecycle and context store** are aligned with it across storage backends.
- Samples **emit consistent telemetry**, so results from different scenarios can be compared in the same reporting shape.
- The **Gemini LLM client is fixed** for live runs.
- The documentation build gets **dedicated requirements and pipeline updates**.
- **Version 0.2.0** is released (2026-05-20).

---

## 2026-06-02 — Meta-context sample matured

- The **meta-context engineering sample (88)** is restructured into a clear chain: **intent, DIR boundaries, threat model, acceptance criteria, coding standards, and a context-compiler prompt**.
- A runnable **context compiler** and **Semgrep rules** (agent isolation, kernel determinism, security) turn those artefacts into **automatically enforceable checks**.

---

## 2026-06-09 — Semantic governance and “The Compliant Lie”

- New material on **semantic governance** explains how an agent can follow every formal rule and still mislead, and what evidence the runtime must demand to catch it.
- Two samples demonstrate it: **12 Compliant Lie** and **39 Fintech Evidence Governance** (alignment checks, approval monitoring, evidence-backed decisions).
- Long-form documents are **published as web pages only**; the duplicate PDF exports are removed, and the site navigation and sample pages are corrected.

---

## 2026-06-26 to 2026-06-30 — Persisted decision ledger and “architecture of trust”

- A **`decision_ledger_entries` table** joins the reference data model, and the ledger gains persistence in every storage backend, so **pre-commit intent (PCI) records survive restarts** and can be audited later. Insurance and fintech samples use it.
- **Version 0.3.0** is released.
- The **retention airlock sample (40)** shows several validation types working together: evidence checks, a context tax, reconstruction of agent claims, and temporal monitoring.

---

## 2026-07-06 — Agentic DMZ security pattern

- The **Agentic DMZ** is introduced to stop attackers from extracting intellectual property or probing rules through agent responses:
  - a new **`INTERFACE` role** with strict context starvation;
  - a kernel-level **outbound translation gate** that neutralises detailed DIM rejections, defeating oracle and fuzzing attacks;
  - the invariant **“disclosure is a side effect”**, with information-flow controls for the event bus.
- The ROA manifesto, DIR pattern, topologies, and minified specification are updated accordingly.

---

## 2026-07-21 to 2026-07-29 — LLM configuration and a clearer LDS order

- The **Gemini client is updated**, and **LLM configuration uses placeholders**, so no credentials or vendor choices are baked into samples.
- The five **Legal Decision State (LDS)** dimensions are **reordered as Authority, Context, Time, Intent, Evidence (“ACTIE”)** across the README and all long-form documents, and the LDS graphic is refreshed, so the figures match the text.

---

## 2026-07-31 — Contract Studio

- **Contract Studio** is added as a tool for **bootstrapping contracts**: guided interview, LLM-assisted drafting, a **web UI**, CLI, rendering to YAML, integrity checks, and import from existing samples. Teams no longer have to hand-write contracts from scratch.

---

## 2026-08-11 to 2026-08-18 — Invariant-driven governance and a unified Contract Studio

- Documentation integrates **invariant-driven governance**:
  - **build-time human-in-the-loop review** and **intent compression** govern rules generated by LLMs;
  - **boundaries** (topology and structure) are separated from **invariants** (state and logic);
  - the DIM is modelled as a **kernel invariant evaluator** whose limits follow from Rice’s theorem;
  - **ex-post governance (circuit breakers)** is required because the world is open;
  - **tooling** (coverage matrix, SMT solvers) is defined to prevent rubber-stamping;
  - the minified specification is synchronised as the single AI-context reference.
- Contract Studio gains **unified configuration**, **manual YAML editing**, an **invariant ontology**, **governance authoring rules**, and **stricter validation of aggregate policies**; a parsing defect in the LLM interview is fixed.
- The runtime **projects canonical contracts** into its own model, and all samples load contracts through a **shared provider**.
- Test coverage grows to include the contract tool, governance validation, the runtime, PostgreSQL repository, and ledger storage.

---

## 2026-09-22 — Dynamic invariants

- The runtime now supports **dynamic invariants**: invariants are **compiled** from contracts, evaluated by the DIM, and **amended** under control, instead of being hard-coded in each sample.
- The **insurance underwriting sample** is migrated to contract-driven invariants (its bespoke gate module is removed), and a **finance trading contract** is added.
- Documentation across the manifesto, pattern, topologies, governance, minified spec, and Context as Code is **reconciled** so every document describes the same model.
- New tests cover invariants, the insurance agent and reports, LLM JSON parsing, and logging.

---

## 2026-10-08 to 2026-11-09 — Version 0.4.0 and a cleaner runtime boundary

- **Version 0.4.0** is released (2026-10-08).
- A Contract Studio fix aligns the **governance context, LLM interview, and schema**.
- The runtime **no longer depends on Contract Studio**: canonical-contract handling moves into `dir_core` (contract projection and a responsibility adapter) and the samples’ shared contract helpers are slimmed down. Adopters can use the library without the authoring tool.
- New tests guard this boundary (**samples isolation**, **responsibility adapter**), and the READMEs for the package, samples, and the tool are updated.
