"""
Hook Generator — SAFE OS Domain Hook Builder
=============================================
Generates domain-specific hooks for SAFE OS extensions.
Each hook maps to one of the 3 tiers: Preservation, Verification, Reflexive.

Usage:
    from hook_generator import ClaudeCLIHookGenerator
    
    gen = ClaudeCLIHookGenerator()
    gen.generate_domain_hooks("Rally")
    gen.add_hook("Rally disbanded", "Preservation", "A rally club has shut down.", domain_tag="Rally", priority=8)
    
    hooks = gen.list_hooks()
"""

import datetime
from typing import List, Dict, Optional


class Hook:
    def __init__(self, name: str, tier: str, description: str,
                 domain_tag: Optional[str] = None, priority: int = 5):
        self.name = name
        self.tier = tier  # e.g., 'Preservation', 'Verification', 'Reflexive'
        self.description = description
        self.domain_tag = domain_tag
        self.priority = priority
        self.timestamp = datetime.datetime.utcnow()

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "tier": self.tier,
            "description": self.description,
            "domain_tag": self.domain_tag,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat() + "Z"
        }


class ClaudeCLIHookGenerator:
    def __init__(self):
        self.hooks: List[Hook] = []

    def add_hook(self, name: str, tier: str, description: str,
                 domain_tag: Optional[str] = None, priority: int = 5):
        hook = Hook(name, tier, description, domain_tag, priority)
        self.hooks.append(hook)
        print(f"[CLI Hook Added] {hook.name} | Tier: {hook.tier} | Domain: {hook.domain_tag}")

    def list_hooks(self) -> List[Dict]:
        return [hook.to_dict() for hook in self.hooks]

    def generate_domain_hooks(self, domain_name: str) -> None:
        """Automatically suggest default hooks for a new domain"""
        self.add_hook(
            name=f"{domain_name} entity created",
            tier="Preservation",
            description=f"A new {domain_name} entity has been recorded in the system.",
            domain_tag=domain_name,
            priority=4
        )
        self.add_hook(
            name=f"{domain_name} verification needed",
            tier="Verification",
            description=f"A new {domain_name} entity requires verification against sources.",
            domain_tag=domain_name,
            priority=5
        )
        self.add_hook(
            name=f"{domain_name} context updated",
            tier="Reflexive",
            description=f"Meta/contextual information updated for {domain_name}.",
            domain_tag=domain_name,
            priority=3
        )

    def to_claude_hooks_list(self) -> List[str]:
        """Return hook names as a plain list for DomainConfig.hooks"""
        return [h.name for h in self.hooks]


if __name__ == "__main__":
    import sys
    domain = sys.argv[1] if len(sys.argv) > 1 else "Example"
    gen = ClaudeCLIHookGenerator()
    gen.generate_domain_hooks(domain)
    print("\nGenerated hooks:")
    for h in gen.list_hooks():
        print(f"  [{h['tier']}] {h['name']} (priority={h['priority']})")
    print(f"\nDomainConfig.hooks = {gen.to_claude_hooks_list()}")
