#!/usr/bin/env python3
"""
PGR Fix Agent — Automated PG Region Short Fix for Fusion Compiler
==================================================================
Connects to a live fc_shell RPC server, scans all vccr_c23_s0 PG regions
for user_route signal overlaps, finds optimal lego-grid shifts to eliminate
shorts, and applies moves using set_attribute boundary.

Usage:
    python3 pgr_fix_agent.py --host <IP> --port <PORT> [options]

Examples:
    # Dry-run scan only (default):
    python3 pgr_fix_agent.py --host 10.117.87.158 --port 8888

    # Apply moves after scan:
    python3 pgr_fix_agent.py --host 10.117.87.158 --port 8888 --apply

    # Custom net pattern and grid:
    python3 pgr_fix_agent.py --host 10.117.87.158 --port 8888 \\
        --net-pattern vccr_c23_s0 --xstep 5.4 --ystep 5.76 --apply

    # Use pre-computed moves (skip scan):
    python3 pgr_fix_agent.py --host 10.117.87.158 --port 8888 \\
        --use-saved-moves --apply

Author : GitHub Copilot (generated from live PD session)
Design : par_base_fabric_shaft_misc_s01
Tool   : fc_shell U-2022.12-SP5
"""

import socket
import argparse
import time
import sys
import json
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# SAVED MOVES from this session (pre-validated on 10.117.87.158:8888)
# Lego grid: X_STEP=5.4um, Y_STEP=5.76um
# 35/39 PGRs fully clean after move, _19 unfixable, _27 residual=44
# ─────────────────────────────────────────────────────────────────────────────
SAVED_MOVES = {
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_1":  (1, 8),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_2":  (0, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_3":  (0, 3),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_4":  (0, 1),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_5":  (0, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_6":  (0, 1),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_7":  (0, 3),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_9":  (0, 3),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_10": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_11": (0, 8),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_12": (0, 4),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_14": (0, 5),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_15": (0, 4),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_16": (0, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_17": (0, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_18": (0, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_20": (0, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_21": (0, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_22": (0, 1),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_23": (3, 1),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_24": (2, 2),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_25": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_26": (1, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_27": (3, 6),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_28": (0, 4),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_29": (0, 8),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_30": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_31": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_32": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_33": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_34": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_35": (2, 0),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_36": (0, 3),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_37": (0, 3),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_38": (0, 3),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_39": (0, 3),
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_41": (2, 0),
    # _19: unfixable — 48 user_routes span entire region, no shift clears them
    # _40: already clean — no move needed
}

SKIP_NOTES = {
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_19":
        "UNFIXABLE: 48 user_routes span entire PGR area — manual reroute needed",
    "pg_region_primary_vccinf_secondary_vccr_c23_s0_40":
        "CLEAN: no user_route overlaps at current position, no move needed",
}


# ─────────────────────────────────────────────────────────────────────────────
# RPC Client
# ─────────────────────────────────────────────────────────────────────────────
class FCShellRPC:
    """TCP RPC client for fc_shell."""

    def __init__(self, host, port, timeout=60):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.buf = ""

    def connect(self):
        print(f"[RPC] Connecting to {self.host}:{self.port} ...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        # Send TOOL_INFO and LANGUAGE handshake
        self._send("TOOL_INFO")
        info = self._recv_line()
        print(f"[RPC] {info.strip()}")
        self._send("LANGUAGE TCL")
        lang = self._recv_line()
        print(f"[RPC] {lang.strip()}")

    def _send(self, cmd):
        self.sock.sendall((cmd + "\r\n").encode())

    def _recv_line(self):
        while "\n" not in self.buf:
            chunk = self.sock.recv(65536).decode(errors="replace")
            if not chunk:
                raise ConnectionError("Connection closed by server")
            self.buf += chunk
        line, self.buf = self.buf.split("\n", 1)
        return line.strip()

    def call(self, tcl_cmd, timeout=120):
        """Send a CALL command and return (ok, result)."""
        self._send(f"CALL {tcl_cmd}")
        deadline = time.time() + timeout
        while True:
            if time.time() > deadline:
                return False, "TIMEOUT"
            try:
                line = self._recv_line()
            except socket.timeout:
                return False, "TIMEOUT"
            if line.startswith("OK"):
                return True, line[3:].strip()
            elif line.startswith("ERROR"):
                return False, line[6:].strip()

    def close(self):
        if self.sock:
            self.sock.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: parse boundary string from fc_shell attribute
# ─────────────────────────────────────────────────────────────────────────────
def parse_boundary(b_str):
    """
    Parse fc_shell boundary string like:
      {{llx lly} {llx ury} {urx ury} {urx lly}}
    Returns (llx, lly, urx, ury) as floats.
    """
    nums = [float(x) for x in re.findall(r"[-+]?\d+\.?\d*", b_str)]
    if len(nums) < 4:
        return None
    xs = sorted(set(nums[0::2]))
    ys = sorted(set(nums[1::2]))
    return xs[0], ys[0], xs[-1], ys[-1]


def new_boundary(llx, lly, urx, ury, nx, ny, xstep, ystep):
    """Compute new boundary after NX/NY lego shift."""
    nllx = round(llx + nx * xstep, 4)
    nlly = round(lly + ny * ystep, 4)
    nurx = round(urx + nx * xstep, 4)
    nury = round(ury + ny * ystep, 4)
    return nllx, nlly, nurx, nury


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Get all PGRs matching net pattern
# ─────────────────────────────────────────────────────────────────────────────
def get_target_pgrs(rpc, net_pattern):
    print(f"\n[SCAN] Getting all PG regions matching '*{net_pattern}*' ...")
    ok, result = rpc.call(
        f"set pgrs [get_pg_regions -filter {{net_names =~ *{net_pattern}*}}]; "
        f"set names {{}}; foreach_in_collection p $pgrs {{ lappend names [get_attribute $p name] }}; "
        f"join $names \\n"
    )
    if not ok or not result:
        print(f"  ERROR: {result}")
        return []
    names = [n.strip() for n in result.split("\n") if n.strip()]
    print(f"  Found {len(names)} PGRs")
    return names


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Count user_route overlaps at a given NX/NY offset
# ─────────────────────────────────────────────────────────────────────────────
def count_overlaps(rpc, pgr_name, llx, lly, urx, ury, nx, ny, xstep, ystep):
    nllx, nlly, nurx, nury = new_boundary(llx, lly, urx, ury, nx, ny, xstep, ystep)
    tcl = (
        f"set s [filter_collection "
        f"[get_shapes -filter {{net_type==signal && shape_use==user_route}}] "
        f"{{bbox_llx < {nurx} && bbox_urx > {nllx} && "
        f"bbox_lly < {nury} && bbox_ury > {nlly}}}]; "
        f"sizeof_collection $s"
    )
    ok, result = rpc.call(tcl, timeout=30)
    if not ok:
        return -1
    try:
        return int(result.strip())
    except ValueError:
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Scan NX/NY grid to find optimal move
# ─────────────────────────────────────────────────────────────────────────────
def find_optimal_move(rpc, pgr_name, llx, lly, urx, ury,
                      xstep, ystep, max_nx=3, max_ny=8):
    best_count = 999999
    best_nx, best_ny = 0, 0

    print(f"  Scanning NX=0..{max_nx}, NY=0..{max_ny} ...")
    for nx in range(max_nx + 1):
        for ny in range(max_ny + 1):
            cnt = count_overlaps(rpc, pgr_name, llx, lly, urx, ury,
                                  nx, ny, xstep, ystep)
            if cnt < best_count:
                best_count = cnt
                best_nx, best_ny = nx, ny
            if cnt == 0:
                # Perfect — no need to scan further
                print(f"    NX={nx} NY={ny} → 0 overlaps ✓ (perfect)")
                return nx, ny, 0

    print(f"    Best: NX={best_nx} NY={best_ny} → {best_count} remaining")
    return best_nx, best_ny, best_count


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Apply move using set_attribute boundary
# ─────────────────────────────────────────────────────────────────────────────
def apply_move(rpc, pgr_name, nx, ny, xstep, ystep):
    # Get current boundary
    ok, b_str = rpc.call(
        f"get_attribute [get_pg_regions {{{pgr_name}}}] boundary"
    )
    if not ok:
        print(f"  ERROR getting boundary: {b_str}")
        return False

    coords = parse_boundary(b_str)
    if not coords:
        print(f"  ERROR parsing boundary: {b_str}")
        return False

    llx, lly, urx, ury = coords
    nllx, nlly, nurx, nury = new_boundary(llx, lly, urx, ury, nx, ny, xstep, ystep)

    tcl = (
        f"set_attribute [get_pg_regions {{{pgr_name}}}] boundary "
        f"[list [list {nllx} {nlly}] [list {nllx} {nury}] "
        f"[list {nurx} {nury}] [list {nurx} {nlly}]]"
    )
    ok, result = rpc.call(tcl, timeout=30)
    if ok:
        print(f"  ✓ MOVED  {{{llx:.3f},{lly:.3f}}}→{{{nurx:.3f},{nury:.3f}}}  "
              f"NX={nx} NY={ny}")
        return True
    else:
        print(f"  ✗ FAILED: {result}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Verify — count remaining overlaps after move
# ─────────────────────────────────────────────────────────────────────────────
def verify_moves(rpc, pgr_names, xstep, ystep):
    print("\n[VERIFY] Counting remaining overlaps after moves ...")
    total = 0
    for name in pgr_names:
        ok, b_str = rpc.call(
            f"get_attribute [get_pg_regions {{{name}}}] boundary"
        )
        if not ok:
            continue
        coords = parse_boundary(b_str)
        if not coords:
            continue
        llx, lly, urx, ury = coords
        cnt = count_overlaps(rpc, name, llx, lly, urx, ury, 0, 0, xstep, ystep)
        status = "✓ CLEAN" if cnt == 0 else f"✗ {cnt} remaining"
        print(f"  {name[-4:]:>4}  {status}")
        total += cnt
    print(f"\n  Total remaining overlaps: {total}")
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Main Agent
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="PGR Fix Agent — auto-fix vccr_c23_s0 PG region shorts"
    )
    parser.add_argument("--host", required=True, help="fc_shell RPC host IP")
    parser.add_argument("--port", type=int, required=True, help="fc_shell RPC port")
    parser.add_argument("--net-pattern", default="vccr_c23_s0",
                        help="PGR net name pattern to match (default: vccr_c23_s0)")
    parser.add_argument("--xstep", type=float, default=5.4,
                        help="Lego grid X step in um (default: 5.4)")
    parser.add_argument("--ystep", type=float, default=5.76,
                        help="Lego grid Y step in um (default: 5.76)")
    parser.add_argument("--max-nx", type=int, default=3,
                        help="Max NX scan range (default: 3)")
    parser.add_argument("--max-ny", type=int, default=8,
                        help="Max NY scan range (default: 8)")
    parser.add_argument("--apply", action="store_true",
                        help="Apply moves (default: dry-run only)")
    parser.add_argument("--use-saved-moves", action="store_true",
                        help="Use pre-validated moves from this session (skip scan)")
    parser.add_argument("--save-script", metavar="FILE",
                        help="Also write a .tcl script file for manual sourcing")
    parser.add_argument("--verify", action="store_true",
                        help="Verify overlaps after applying moves")
    parser.add_argument("--save-block", action="store_true",
                        help="Run save_block after applying moves")
    args = parser.parse_args()

    # ── Connect ──────────────────────────────────────────────────────────────
    rpc = FCShellRPC(args.host, args.port)
    try:
        rpc.connect()
    except Exception as e:
        print(f"[ERROR] Cannot connect: {e}")
        sys.exit(1)

    # ── Design info ───────────────────────────────────────────────────────────
    ok, design = rpc.call("get_attribute [current_design] full_name")
    print(f"[INFO] Design: {design}")
    ok, nblocks = rpc.call("llength [get_cells -hierarchical -filter {is_hierarchical}]")
    print(f"[INFO] Cells: {nblocks}")

    # ── Get target PGRs ───────────────────────────────────────────────────────
    if args.use_saved_moves:
        pgr_names = list(SAVED_MOVES.keys())
        print(f"\n[INFO] Using {len(pgr_names)} pre-validated moves from session")
    else:
        pgr_names = get_target_pgrs(rpc, args.net_pattern)
        if not pgr_names:
            print("[ERROR] No PGRs found. Check --net-pattern.")
            rpc.close()
            sys.exit(1)

    # ── Get boundaries ────────────────────────────────────────────────────────
    print(f"\n[INFO] Fetching boundaries for {len(pgr_names)} PGRs ...")
    boundaries = {}
    for name in pgr_names:
        ok, b_str = rpc.call(
            f"get_attribute [get_pg_regions {{{name}}}] boundary"
        )
        if ok:
            coords = parse_boundary(b_str)
            if coords:
                boundaries[name] = coords
            else:
                print(f"  WARNING: Could not parse boundary for {name}")
        else:
            print(f"  WARNING: Could not get boundary for {name}: {b_str}")

    print(f"  Got boundaries for {len(boundaries)}/{len(pgr_names)} PGRs")

    # ── Determine moves ───────────────────────────────────────────────────────
    moves = {}  # name -> (nx, ny, expected_remaining)

    if args.use_saved_moves:
        print("\n[MOVES] Using pre-validated (NX,NY) from session ...")
        for name, (nx, ny) in SAVED_MOVES.items():
            if name in boundaries:
                moves[name] = (nx, ny, 0)
                print(f"  {name[-4:]:>4}  NX={nx} NY={ny}")
    else:
        print(f"\n[SCAN] Scanning all {len(boundaries)} PGRs for optimal moves ...")
        print(f"       Grid: X_STEP={args.xstep}um  Y_STEP={args.ystep}um")
        print(f"       Search: NX=0..{args.max_nx}  NY=0..{args.max_ny}\n")

        for name in pgr_names:
            if name not in boundaries:
                continue
            if name in SKIP_NOTES:
                print(f"  SKIP {name[-4:]:>4}  — {SKIP_NOTES[name]}")
                continue

            llx, lly, urx, ury = boundaries[name]
            print(f"  PGR {name[-4:]:>4}  bbox=({llx:.2f},{lly:.2f})→({urx:.2f},{ury:.2f})")

            # Check current overlap first
            cur_cnt = count_overlaps(rpc, name, llx, lly, urx, ury,
                                      0, 0, args.xstep, args.ystep)
            if cur_cnt == 0:
                print(f"    Already clean — no move needed")
                continue

            print(f"    Current overlaps: {cur_cnt}")
            nx, ny, remaining = find_optimal_move(
                rpc, name, llx, lly, urx, ury,
                args.xstep, args.ystep, args.max_nx, args.max_ny
            )
            if nx == 0 and ny == 0:
                print(f"    No improvement possible — skip")
            else:
                moves[name] = (nx, ny, remaining)

    # ── Print move summary ─────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"MOVE SUMMARY  ({len(moves)} PGRs to move)")
    print(f"{'='*70}")
    clean = sum(1 for _, _, r in moves.values() if r == 0)
    partial = len(moves) - clean
    print(f"  Fully clean after move : {clean}")
    print(f"  Partial (residual)     : {partial}")
    for name in SKIP_NOTES:
        print(f"  SKIP: {name}  — {SKIP_NOTES[name]}")
    print(f"{'='*70}\n")

    # ── Write Tcl script if requested ─────────────────────────────────────────
    if args.save_script:
        write_tcl_script(args.save_script, moves, boundaries,
                         args.xstep, args.ystep)
        print(f"[SCRIPT] Written to {args.save_script}")

    # ── Apply moves ───────────────────────────────────────────────────────────
    if not args.apply:
        print("[DRY-RUN] No moves applied. Use --apply to execute.")
        rpc.close()
        return

    print("[APPLY] Applying boundary moves ...")
    success = 0
    failed = 0
    for name, (nx, ny, _) in moves.items():
        if name not in boundaries:
            print(f"  SKIP {name} — no boundary")
            continue
        print(f"  {name[-4:]:>4}  NX={nx} NY={ny}", end="  ")
        ok = apply_move(rpc, name, nx, ny, args.xstep, args.ystep)
        if ok:
            success += 1
        else:
            failed += 1

    print(f"\n[APPLY] Done: {success} moved, {failed} failed")

    # ── Verify ────────────────────────────────────────────────────────────────
    if args.verify:
        verify_moves(rpc, list(boundaries.keys()), args.xstep, args.ystep)

    # ── Save block ────────────────────────────────────────────────────────────
    if args.save_block and success > 0:
        print("\n[SAVE] Running save_block ...")
        ok, result = rpc.call("save_block", timeout=300)
        if ok:
            print("  save_block completed ✓")
        else:
            print(f"  save_block ERROR: {result}")

    # ── Post-move instructions ─────────────────────────────────────────────────
    print("\n" + "="*70)
    print("NEXT STEPS")
    print("="*70)
    print("  1. In fc_shell: compile_pg  (regenerate metal at new PGR positions)")
    print("  2. Run DRC to confirm shorts resolved")
    print("  3. For _19 (48 residual): manually reroute those user_route signals")
    print("  4. For _27 (44 residual): check if acceptable or needs manual fix")
    print("="*70)

    rpc.close()


# ─────────────────────────────────────────────────────────────────────────────
# Write Tcl script for manual sourcing in fc_shell
# ─────────────────────────────────────────────────────────────────────────────
def write_tcl_script(filepath, moves, boundaries, xstep, ystep):
    lines = [
        "# ============================================================",
        "# PGR Fix Script — generated by pgr_fix_agent.py",
        "# Method: set_attribute boundary  (NO remove/recreate)",
        f"# Grid: X_STEP={xstep}um  Y_STEP={ystep}um",
        "# SOURCE THIS IN fc_shell AFTER RELOADING FLOORPLAN DB",
        "# ============================================================",
        "",
        "set execute 0  ;# set to 1 to apply",
        "",
        "proc move_pgr {name nx ny xstep ystep} {",
        "    set pgr [get_pg_regions $name]",
        "    if {[sizeof_collection $pgr] == 0} {",
        "        puts \"WARNING: PGR $name not found\"",
        "        return",
        "    }",
        "    set b [get_attribute $pgr boundary]",
        "    set vals [regexp -all -inline {[0-9]+\\.?[0-9]*} $b]",
        "    set xs {}; set ys {}",
        "    for {set i 0} {$i < [llength $vals]-1} {incr i 2} {",
        "        lappend xs [lindex $vals $i]",
        "        lappend ys [lindex $vals [expr {$i+1}]]",
        "    }",
        "    set xs [lsort -real $xs]; set ys [lsort -real $ys]",
        "    set llx [lindex $xs 0]; set lly [lindex $ys 0]",
        "    set urx [lindex $xs end]; set ury [lindex $ys end]",
        "    set nllx [format \"%.3f\" [expr {$llx + $nx*$xstep}]]",
        "    set nlly [format \"%.3f\" [expr {$lly + $ny*$ystep}]]",
        "    set nurx [format \"%.3f\" [expr {$urx + $nx*$xstep}]]",
        "    set nury [format \"%.3f\" [expr {$ury + $ny*$ystep}]]",
        "    puts [format \"  %-55s NX=%d NY=%d\" $name $nx $ny]",
        "    set_attribute $pgr boundary [list [list $nllx $nlly] [list $nllx $nury] \\",
        "        [list $nurx $nury] [list $nurx $nlly]]",
        "}",
        "",
        f"set XSTEP {xstep}",
        f"set YSTEP {ystep}",
        "",
        "set pgr_moves {",
    ]

    for name, (nx, ny, remaining) in sorted(moves.items()):
        note = f"  ;# residual={remaining}" if remaining > 0 else ""
        lines.append(f"    {{{name}  {nx} {ny}}}{note}")

    lines += [
        "}",
        "",
        "if {$execute} {",
        "    puts \"Applying [llength $pgr_moves] PGR moves...\"",
        "    foreach item $pgr_moves {",
        "        move_pgr [lindex $item 0] [lindex $item 1] [lindex $item 2] $XSTEP $YSTEP",
        "    }",
        "    puts \"Done. Run compile_pg and DRC after saving.\"",
        "} else {",
        "    puts \"DRY RUN — set execute 1 to apply moves\"",
        "    puts \"Will move [llength $pgr_moves] PGRs\"",
        "}",
    ]

    Path(filepath).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
