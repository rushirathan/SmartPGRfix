# SmartPGRfix

**Intelligent Python agent for automatically detecting and fixing DRC shorts between Power Grid (PG) regions and signal `user_route` nets in Synopsys Fusion Compiler (`fc_shell`) physical design flows.**

---

## What It Does

In hierarchical PD flows, PG regions (`pg_region`) containing power nets like `vccr_c23_s0` can overlap with pre-existing `user_route` signal shapes on the same metal layers — causing DRC shorts. Manually finding and fixing these is tedious and error-prone.

**SmartPGRfix** automates the entire workflow:

```
fc_shell (live RPC)
        │
        ▼
① Get all PG regions matching target net (e.g. vccr_c23_s0)
        │
        ▼
② Scan each PGR — count user_route signal overlaps at current position
        │
        ▼
③ Search NX=0..3, NY=0..8 lego-grid offsets → find minimum overlap position
        │
        ▼
④ Apply move via set_attribute boundary  (safe — no remove/recreate)
        │
        ▼
⑤ Verify post-move overlap count
        │
        ▼
⑥ save_block  (optional)
```

---

## Background — Why This Approach

### The Problem
- PG regions are placed at floorplan stage before detailed routing
- `user_route` signal shapes (pre-routed critical nets) are already present
- PGR placement can accidentally overlap these shapes → **DRC short**

### The Fix — Lego Grid Shifts
PG regions must snap to the **lego grid** (site-row multiples):
- `X_STEP = 5.4 µm`  (width of one lego column)
- `Y_STEP = 5.76 µm` (24 rows × 0.24 µm site height)

The agent tries all integer multiples `(NX × 5.4, NY × 5.76)` and picks the shift that minimizes overlap count.

### Critical Discovery — Correct Move Method
> ⚠️ **`remove_pg_regions` + `create_pg_region` approach DOES NOT WORK** — `create_pg_region` fails silently in floorplan-stage DBs and permanently deletes PGRs.

The **only safe method** is:
```tcl
set_attribute [get_pg_regions <name>] boundary <new_bbox>
```
This moves the PGR in-place with no risk of data loss.

---

## Files

| File | Description |
|------|-------------|
| `pgr_fix_agent.py` | Main Python agent — full auto scan + fix |
| `move_pgr_correct.tcl` | Pre-validated Tcl script for direct fc_shell sourcing |
| `README.md` | This file |

---

## Requirements

- Python 3.6+
- No external packages required (stdlib only: `socket`, `argparse`, `re`)
- Synopsys Fusion Compiler `fc_shell` with RPC server enabled
- Design must be at **floorplan stage** with PG regions present

---

## Usage

### Mode 1 — Use Pre-Validated Moves (fastest, same design)
```bash
python3 pgr_fix_agent.py \
  --host 10.117.87.158 --port 8888 \
  --use-saved-moves \
  --apply --verify --save-block
```

### Mode 2 — Auto Scan (new designs / different PGRs)
```bash
python3 pgr_fix_agent.py \
  --host <IP> --port <PORT> \
  --net-pattern vccr_c23_s0 \
  --xstep 5.4 --ystep 5.76 \
  --apply --verify --save-block
```

### Mode 3 — Dry Run Only (see what would move, no changes)
```bash
python3 pgr_fix_agent.py \
  --host <IP> --port <PORT> \
  --net-pattern vccr_c23_s0
```

### Mode 4 — Generate Tcl Script for Manual Sourcing
```bash
python3 pgr_fix_agent.py \
  --host <IP> --port <PORT> \
  --use-saved-moves \
  --save-script /tmp/pgr_moves.tcl
```
Then in `fc_shell`:
```tcl
set execute 1
source /tmp/pgr_moves.tcl
```

---

## All Options

```
--host HOST              fc_shell RPC host IP               [required]
--port PORT              fc_shell RPC port                  [required]
--net-pattern PATTERN    PGR net name to match              [default: vccr_c23_s0]
--xstep FLOAT            Lego X step in µm                  [default: 5.4]
--ystep FLOAT            Lego Y step in µm                  [default: 5.76]
--max-nx INT             Max NX scan range                  [default: 3]
--max-ny INT             Max NY scan range                  [default: 8]
--apply                  Apply moves (default: dry-run)
--use-saved-moves        Use pre-validated moves, skip scan
--save-script FILE       Write Tcl script to FILE
--verify                 Count overlaps after applying moves
--save-block             Run save_block after moves
```

---

## Design Reference

Validated on:

| Property | Value |
|----------|-------|
| Tool | Synopsys Fusion Compiler `U-2022.12-SP5` |
| Design | `par_base_fabric_shaft_misc_s01` |
| Stage | Floorplan |
| PGRs scanned | 39 primary `vccr_c23_s0` PG regions |
| Result | 35/39 fully clean, 2 partially fixed, 2 skipped |

### Per-PGR Results (pre-validated)

| PGR | NX | NY | Result |
|-----|----|-----|--------|
| `_1` | 1 | 8 | ✅ Clean |
| `_2` – `_7` | 0 | 1–3 | ✅ Clean |
| `_10`,`_25`,`_30`–`_35`,`_41` | 2 | 0 | ✅ Clean |
| `_11`,`_29` | 0 | 8 | ✅ Clean |
| `_12`,`_15`,`_28` | 0 | 4 | ✅ Clean |
| `_14` | 0 | 5 | ✅ Clean |
| `_19` | — | — | ❌ Unfixable — 48 user_routes span entire region |
| `_23` | 3 | 1 | ⚠️ 2 remaining |
| `_27` | 3 | 6 | ⚠️ 44 remaining |
| `_40` | — | — | ✅ Already clean, no move |

---

## RPC Protocol (fc_shell)

```
TCP socket — lines terminated with \r\n
Handshake:  TOOL_INFO → OK ...
            LANGUAGE TCL → OK
Commands:   CALL <tcl_expression>
Response:   OK <result>   or   ERROR <message>
```

> **Note:** `ERROR` is always ALL-CAPS in fc_shell responses.

---

## After Applying Moves

```tcl
# 1. Regenerate physical PG metal at new PGR positions
compile_pg

# 2. Save the block
save_block

# 3. Run DRC to confirm shorts resolved
verify_pg_net_connectivity -check_pg_regions

# 4. For _19 (unfixable by shift): manually reroute those user_route signals
#    to detour around the PGR boundary
```

---

## License

MIT License — free to use, modify, and distribute.
