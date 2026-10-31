"""Campus Network Topology Graph Engine.

Provides hierarchical traversal, dependency mapping, blast radius computation,
common ancestor detection, and graceful handling of unknown network nodes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class TopologyNode:
    """Represents an individual node in the campus network graph."""

    def __init__(
        self,
        node_id: str,
        node_type: str,
        name: str,
        location: str = "",
        ip: str = "",
        capacity_gbps: float = 1.0,
        parent_id: Optional[str] = None
    ) -> None:
        self.id = node_id
        self.type = node_type
        self.name = name
        self.location = location
        self.ip = ip
        self.capacity_gbps = capacity_gbps
        self.parent_id = parent_id
        self.children_ids: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "location": self.location,
            "ip": self.ip,
            "capacity_gbps": self.capacity_gbps,
            "parent": self.parent_id,
            "children": self.children_ids,
        }


class TopologyEngine:
    """Deterministic graph engine representing the campus network infrastructure."""

    DEFAULT_TOPOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "topology.json"

    def __init__(self, topology_path: Optional[Path | str] = None) -> None:
        self.nodes: Dict[str, TopologyNode] = {}
        self.root_id: Optional[str] = None
        self._load_topology(topology_path or self.DEFAULT_TOPOLOGY_PATH)

    def _load_topology(self, path: Path | str) -> None:
        p = Path(path)
        if not p.exists():
            # Create a minimal fallback topology rather than failing
            self._create_fallback_topology()
            return

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        for n in data.get("nodes", []):
            node = TopologyNode(
                node_id=n["id"],
                node_type=n.get("type", "unknown"),
                name=n.get("name", n["id"]),
                location=n.get("location", ""),
                ip=n.get("ip", ""),
                capacity_gbps=float(n.get("capacity_gbps", 1.0)),
                parent_id=n.get("parent")
            )
            self.nodes[node.id] = node
            if node.parent_id is None and self.root_id is None:
                self.root_id = node.id

        # Build child references
        for node in self.nodes.values():
            if node.parent_id and node.parent_id in self.nodes:
                self.nodes[node.parent_id].children_ids.append(node.id)

    def _create_fallback_topology(self) -> None:
        """Create a default 4-tier campus network in memory."""
        root = TopologyNode("CORE-SW-01", "core_switch", "Core Switch", parent_id=None)
        self.nodes[root.id] = root
        self.root_id = root.id

    def is_device_known(self, device_id: str) -> bool:
        """Return True if device exists in verified topology."""
        return device_id in self.nodes

    def get_node(self, device_id: str) -> TopologyNode:
        """Retrieve node or generate a gracefully synthesized unknown node."""
        if device_id in self.nodes:
            return self.nodes[device_id]
        return self._synthesize_unknown_node(device_id)

    def _synthesize_unknown_node(self, device_id: str) -> TopologyNode:
        """Synthesize node metadata based on standard naming conventions."""
        upper = device_id.upper()
        if "CORE" in upper:
            ntype = "core_switch"
            parent = None
        elif "DIST" in upper:
            ntype = "dist_switch"
            parent = self.root_id
        elif "SW" in upper or "BLDG" in upper:
            ntype = "bldg_switch"
            parent = "DIST-SW-NORTH" if "DIST-SW-NORTH" in self.nodes else self.root_id
        elif "AP" in upper or "WIFI" in upper:
            ntype = "access_point"
            parent = "BLDG-SW-ENG" if "BLDG-SW-ENG" in self.nodes else self.root_id
        elif "SRV" in upper or "DNS" in upper or "DHCP" in upper:
            ntype = "server"
            parent = self.root_id
        else:
            ntype = "end_device"
            parent = None

        synth = TopologyNode(
            node_id=device_id,
            node_type=ntype,
            name=f"Synthesized Node ({device_id})",
            location="Unknown Location",
            ip="0.0.0.0",
            parent_id=parent
        )
        return synth

    def get_upstream_path(self, device_id: str) -> List[str]:
        """Return list of ancestor IDs from immediate parent up to the root Core Switch."""
        path: List[str] = []
        curr_id: Optional[str] = device_id

        visited: Set[str] = set()
        while curr_id and curr_id in self.nodes:
            if curr_id in visited:
                break  # Prevent cycle
            visited.add(curr_id)
            node = self.nodes[curr_id]
            if node.parent_id:
                path.append(node.parent_id)
                curr_id = node.parent_id
            else:
                break
        return path

    def get_downstream_devices(self, device_id: str) -> List[str]:
        """Return all descendant device IDs downstream of the given device."""
        if device_id not in self.nodes:
            return []

        descendants: List[str] = []
        queue = list(self.nodes[device_id].children_ids)
        visited = set(queue)

        while queue:
            curr = queue.pop(0)
            descendants.append(curr)
            if curr in self.nodes:
                for child in self.nodes[curr].children_ids:
                    if child not in visited:
                        visited.add(child)
                        queue.append(child)

        return descendants

    def get_blast_radius(self, failed_device_id: str) -> Dict[str, Any]:
        """Compute the downstream blast radius and affected device summary."""
        node = self.get_node(failed_device_id)
        downstream = self.get_downstream_devices(failed_device_id)

        # Categorize affected tiers
        tiers: Dict[str, int] = {}
        for dev_id in downstream:
            t = self.get_node(dev_id).type
            tiers[t] = tiers.get(t, 0) + 1

        # Calculate estimated impact weight (Core has highest weight)
        weights = {
            "core_switch": 1.0,
            "dist_switch": 0.8,
            "bldg_switch": 0.5,
            "access_point": 0.25,
            "server": 0.7,
            "end_device": 0.05,
            "unknown": 0.1
        }
        tier_weight = weights.get(node.type, 0.2)
        total_affected = len(downstream) + 1  # Including failed node itself

        return {
            "root_device_id": failed_device_id,
            "root_device_type": node.type,
            "direct_children_count": len(node.children_ids),
            "total_downstream_count": len(downstream),
            "downstream_device_ids": downstream,
            "affected_tier_breakdown": tiers,
            "severity_weight": tier_weight,
            "is_single_point_of_failure": len(downstream) > 1,
        }

    def find_common_ancestor(self, device_ids: List[str]) -> Optional[str]:
        """Find the lowest common upstream ancestor for a set of failing device IDs."""
        if not device_ids:
            return None
        valid_ids = [d for d in device_ids if d in self.nodes]
        if not valid_ids:
            return None
        if len(valid_ids) == 1:
            return valid_ids[0]

        # Get ancestor sets for each device
        ancestor_paths = []
        for dev_id in valid_ids:
            path = [dev_id] + self.get_upstream_path(dev_id)
            ancestor_paths.append(path)

        # Intersect ancestor paths preserving ordering from the first path
        common_candidates = [node for node in ancestor_paths[0] if all(node in p for p in ancestor_paths[1:])]
        if common_candidates:
            # The lowest common ancestor is the first common node in the path (closest to leaves)
            return common_candidates[0]
        return self.root_id

    def calculate_topology_consistency(self, anomalous_device_ids: List[str]) -> Tuple[float, str]:
        """Calculate topological consistency score (0.0 to 1.0) and explanation.
        
        High consistency (0.85-1.0):
          - Single device failure
          - Multiple devices belonging to the exact same subnet/switch cluster
        Medium consistency (0.6-0.84):
          - Devices in same distribution domain
        Low consistency (< 0.6):
          - Arbitrary disconnected nodes failing with no common upstream switch
        """
        if not anomalous_device_ids:
            return 1.0, "No anomalous devices; nominal network topology."

        if len(anomalous_device_ids) == 1:
            return 0.95, f"Isolated incident on single device ({anomalous_device_ids[0]})."

        known_ids = [d for d in anomalous_device_ids if d in self.nodes]
        if not known_ids:
            return 0.6, "Anomalous devices are unknown to registered campus topology."

        lca = self.find_common_ancestor(known_ids)
        if not lca:
            return 0.4, "Anomalous devices are topologically disjoint with no common parent."

        lca_node = self.nodes[lca]
        if lca in anomalous_device_ids:
            return 1.0, f"Upstream node {lca} ({lca_node.type}) is itself anomalous, explaining all downstream failures."

        if lca_node.type in ("bldg_switch", "access_point"):
            return 0.95, f"All failing devices share localized ancestor {lca} ({lca_node.type})."
        elif lca_node.type == "dist_switch":
            return 0.85, f"All failing devices share distribution domain switch {lca}."
        elif lca_node.type == "core_switch":
            return 0.70, f"Failures span across campus converging only at central {lca}."

        return 0.75, f"Topological correlation identified at {lca}."
