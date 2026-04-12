# Three-Agent Walkthrough — Python vs Go for AI-Coded Projects

A step-by-step tutorial running the redesigned RTC runner with three Claude agents
deliberating toward a shared architectural principle.

## Goal

Produce an **architectural principle** stating when to select **Python** vs **Go**
for future AI-coded projects (i.e. projects where the code is primarily authored
by coding agents).

## Preconditions

- Engine running at `http://localhost:8100`
- `claude` CLI logged in (OAuth, no `ANTHROPIC_API_KEY` required)
- Venv: `~/Environments/roundtable-consensus` activated
- Working dir: `~/Projects/roundtable-consensus`

---

## Step 1 — Generate OCEAN traits

```bash
python3 -m cli.rtc_primer --count 3 --seed 42 --output docs/three_agent_profiles.json
```

Result (seed 42, 3 archetypes round-robined):

| Agent | Archetype | High traits | Low traits |
|---|---|---|---|
| agent-000 | **Leader** | initiative 0.98, self_interest 0.88, sociability 0.86 | compliance 0.39 |
| agent-001 | **Collaborator** | sociability 0.84, consistency 0.79, persuasiveness 0.79 | self_interest 0.31, risk_tolerance 0.40 |
| agent-002 | **Analyst** | compliance 0.98, consistency 0.80 | risk_tolerance 0.11, persuasiveness 0.38, adaptability 0.24 |

**Expected dynamics:** Leader drives a bold proposal; Collaborator tries to bridge;
Analyst pushes rigor and resists risk. Good spread for a PROPOSE→FEEDBACK→REVISE cycle.

## Step 2 — Deliberation topic

> "Define an architectural principle to choose **Python** or **Go** as the
> implementation language for future AI-coded projects."

Agents must converge on a single principle (a heuristic or rule) — not pick one
language outright.

## Step 3 — Run parameters (defaults)

- CP balance: **100** per agent
- `proposal_self_stake`: **10 CP**
- `feedback_stake`: **5 CP**
- `max_feedback_per_agent`: **2**
- Phase tick budgets: propose 3, feedback 3, revise 2, stake 3, finalize 1
- Agent config: `claude-sonnet` (from `agents.yaml`)

## Step 4 — Scenario registration

Start the engine (separate terminal or background):

```bash
python3 -m uvicorn engine.app:app --host 127.0.0.1 --port 8100 --log-level warning
```

Create session + register agents:

```bash
python3 -m cli.rtc_scenario \
  --issue "Python vs Go for AI-coded projects" \
  --profiles docs/three_agent_profiles.json \
  --agents 3 --seed 42 \
  | tee docs/scenario_output.json
```

Result: session `e2fd73df`, 3 agents registered (tokens issued, 100 CP each).

> **Note:** `rtc_scenario` prints human-readable lines before the JSON payload, so
> `scenario_output.json` isn't pure JSON. Extract the registrations with:
>
> ```bash
> python3 -c "import json; raw=open('docs/scenario_output.json').read(); \
>   open('docs/registrations.json','w').write(json.dumps(json.loads(raw[raw.index('{'):])['registrations'], indent=2))"
> ```

## Step 5 — Spawn runners

```bash
python3 -m cli.rtc_spawn \
  --session f55f3843 \
  --profiles docs/registrations.json \
  --agent claude-sonnet
```

Runners listen on ports 8200/8201/8202. `rtc_spawn` now PATCHes each
runner's URL back to the engine via `PATCH /v1/sessions/{sid}/agents/{aid}`
so `RemoteAgentActor.runner_url` gets populated — without this step,
signals silently fall back to `signal_ready`.

> **Gotcha discovered:** the initial design had no way to report runner URLs
> back. Fix committed in `f0333a2`: new PATCH endpoint + rtc_spawn wiring.

## Step 6 — Drive the session

### PROPOSE phase

**Tick 1** kicks the session into PROPOSE and dispatches a signal to each
runner. Each runner spawns a `claude --print --model sonnet` subprocess with
the full mono context. The agent runs, reads the context, uses its Bash tool
to `curl -X POST .../agents/{id}/action` back to the engine.

```bash
curl -s -X POST http://localhost:8100/v1/sessions/f55f3843/tick
```

After ~45s, all three agents had responded (logged in engine):
- `agent-002` → `signal_ready` (Analyst, risk_tolerance 0.11 — declined to propose)
- `agent-001` → `submit_proposal` (Collaborator — Python, ecosystem argument)
- `agent-000` → `submit_proposal` (Leader — Python-first with Go for perf-critical)

**Tick 2** drains the action queue. Two real proposals now in the engine
(see `docs/propose_phase_proposals.json`).

**Observation:** OCEAN profiles shaped behaviour visibly — the low-risk Analyst
deferred, the two higher-initiative agents proposed. Both Python-biased
proposals converged on similar ecosystem/training-corpus reasoning but
differed in decisiveness (hybrid Python+Go vs Python-only).

### FEEDBACK phase

*TBD*

### REVISE phase

*TBD*

### STAKE phase

*TBD*

### FINALIZE phase

*TBD*

## Step 7 — Observations

*TBD — what worked, what surprised us, what broke.*

## Appendix — commands used

```bash
# venv
source ~/Environments/roundtable-consensus/bin/activate

# traits
python3 -m cli.rtc_primer --count 3 --seed 42 --output docs/three_agent_profiles.json
```
