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
