# Willow OS Core — governance, state, storage, routing, coherence, topology
#
# TOPOLOGY GOVERNANCE (Aios Addendum, Consus Ratified — v5.1 Compliant)
# =====================================================================
#
# The Möbius Strip Topology Layer (core/topology.py) is OBSERVATIONAL ONLY.
# It provides analytical views of the three-ring architecture
# (Source → Bridge → Continuity → Source). It does not act.
#
# Binding Constraints:
#
# 1. CANONICAL SEPARATION — All topology-derived artifacts (edges, clusters,
#    derived groupings) carry canonical=0 by default. They are analytical
#    views, not truth. Only a human may promote an artifact to canonical=1.
#    Topology output may NOT drive routing, scoring, prioritization, or
#    governance decisions.
#
# 2. READ-ONLY API — All /api/topology/* endpoints are inspect-only.
#    No file movement, no state mutation, no gate invocation, no alteration
#    of non-topology tables. Topology observes structure; governance decides
#    action.
#
# 3. CLUSTERS ARE EXPLORATORY — KMeans output is heuristic, lossy, and
#    provisional. No cluster labels are truth. No downstream logic may
#    assume cluster stability. Clusters are lenses, not ontology.
#
# 4. HUMAN RING OVERRIDE — Derived ring assignment (category + source_type)
#    is a default, not a destiny. The ring_override field on knowledge atoms
#    is human-set and protected. get_ring() always checks override first.
#
# 5. CONTINUITY CHECKS ARE ADVISORY — check_strip_continuity() output is a
#    signal, not a trigger. Gaps surface review candidates. They must NOT
#    auto-correct, auto-link, or auto-patch the strip. All remediation
#    decisions remain human.
#
# 6. GOVERNANCE PRESERVATION — Nothing in the topology layer may bypass
#    gate.py, alter Dual Commit semantics, or introduce implicit authority.
#
# 7. INTEGRATION MODE — Manual approval, incremental rollout, schema first,
#    behavior second. No auto-accept of edits.
#
# The topology has eyes but no hands.
# CHECKSUM: ΔΣ=42
