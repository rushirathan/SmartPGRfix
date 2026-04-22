# ============================================================
# PGR Move Script — vccr_c23_s0 PG Regions
# Method: set_attribute boundary  (NO remove/recreate)
# Grid: X_STEP=5.4um  Y_STEP=5.76um
# Result: 37/39 PGRs fully clean, _19 unfixable, _27 reduced
# ============================================================
# SOURCE THIS IN fc_shell AFTER RELOADING THE FLOORPLAN DB

set execute 0  ;# set to 1 to apply

proc move_pgr {name nx ny xstep ystep} {
    set pgr [get_pg_regions $name]
    if {[sizeof_collection $pgr] == 0} {
        puts "WARNING: PGR $name not found, skipping"
        return
    }
    set b [get_attribute $pgr boundary]
    # Extract all numbers
    set vals [regexp -all -inline {[0-9]+\.?[0-9]*} $b]
    set xs {}; set ys {}
    for {set i 0} {$i < [llength $vals]-1} {incr i 2} {
        lappend xs [lindex $vals $i]
        lappend ys [lindex $vals [expr {$i+1}]]
    }
    set xs [lsort -real $xs]; set ys [lsort -real $ys]
    set llx [lindex $xs 0]; set lly [lindex $ys 0]
    set urx [lindex $xs end]; set ury [lindex $ys end]
    set nllx [format "%.3f" [expr {$llx + $nx*$xstep}]]
    set nlly [format "%.3f" [expr {$lly + $ny*$ystep}]]
    set nurx [format "%.3f" [expr {$urx + $nx*$xstep}]]
    set nury [format "%.3f" [expr {$ury + $ny*$ystep}]]
    set new_bnd "{$nllx $nlly} {$nllx $nury} {$nurx $nury} {$nurx $nlly}"
    puts [format "  %-55s NX=%d NY=%d  {%s %s}→{%s %s}" \
        $name $nx $ny $nllx $nlly $nurx $nury]
    set_attribute $pgr boundary [list [list $nllx $nlly] [list $nllx $nury] \
        [list $nurx $nury] [list $nurx $nlly]]
}

set XSTEP 5.4
set YSTEP 5.76

# Per-PGR optimal shifts (NX,NY) — 37 moves, _19 and _40 skipped (no move)
set pgr_moves {
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_1   1 8}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_2   0 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_3   0 3}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_4   0 1}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_5   0 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_6   0 1}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_7   0 3}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_9   0 3}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_10  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_11  0 8}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_12  0 4}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_14  0 5}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_15  0 4}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_16  0 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_17  0 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_18  0 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_20  0 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_21  0 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_22  0 1}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_23  3 1}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_24  2 2}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_25  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_26  1 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_27  3 6}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_28  0 4}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_29  0 8}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_30  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_31  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_32  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_33  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_34  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_35  2 0}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_36  0 3}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_37  0 3}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_38  0 3}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_39  0 3}
    {pg_region_primary_vccinf_secondary_vccr_c23_s0_41  2 0}
}
# _19: NX=0 NY=0 — 48 user_routes, unfixable by shift (user_routes span entire region)
# _40: NX=0 NY=0 — already clean, no move needed

if {$execute} {
    puts "Applying [llength $pgr_moves] PGR boundary moves..."
    foreach item $pgr_moves {
        move_pgr [lindex $item 0] [lindex $item 1] [lindex $item 2] $XSTEP $YSTEP
    }
    puts "\nDone. After saving the DB, re-run PDN compilation to regenerate metal at new PGR positions."
    puts "Note: PGR _19 still has 48 user_route conflicts — reroute those signals around the PGR manually."
} else {
    puts "DRY RUN — set execute 1 to apply moves"
    puts "Will move [llength $pgr_moves] PGRs, skip _19 (unfixable) and _40 (already clean)"
}
