#!/usr/bin/env python3
"""
11_topology_c_dl_pci - Decision Ledger & Proof-Carrying Intents (PCI).

DIR §2.4 / Topologies C.
Scenario: High-stakes decision (e.g. fund transfer) requiring auditability and non-repudiation.

Key components:
1. Decision Ledger: Append-only, tamper-evident log (Merkle-chain style).
2. PCI (Proof-Carrying Intent): Intent includes cryptographic signature and context hash.
"""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from dir_runtime import new_dfid

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# --- 1. Cryptographic Primitives (Simulated) ---

def sign_data(secret_key: bytes, data: str) -> str:
    """HMAC-SHA256 signature."""
    return hmac.new(secret_key, data.encode(), hashlib.sha256).hexdigest()

def verify_signature(secret_key: bytes, data: str, signature: str) -> bool:
    expected = sign_data(secret_key, data)
    return hmac.compare_digest(expected, signature)

def hash_content(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


# --- 2. The Chain (Decision Ledger) ---

@dataclass
class LedgerEntry:
    index: int
    prev_hash: str
    timestamp: float
    data: Dict[str, Any] # The PCI
    entry_hash: str

class DecisionLedger:
    def __init__(self):
        self.chain: List[LedgerEntry] = []
        # Genesis block
        self.chain.append(LedgerEntry(0, "0"*64, time.time(), {"msg": "GENESIS"}, self._hash_entry(0, "0"*64, {}, time.time())))

    def _hash_entry(self, index: int, prev_hash: str, data: Dict, timestamp: float) -> str:
        payload = f"{index}|{prev_hash}|{timestamp}|{hash_content(data)}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def append(self, pci: Dict[str, Any]) -> bool:
        """
        Append PCI to ledger.
        Returns True if accepted (valid format), False otherwise.
        Note: Deep verification of PCI happens before or during append.
        """
        prev = self.chain[-1]
        index = prev.index + 1
        ts = time.time()
        entry_hash = self._hash_entry(index, prev.entry_hash, pci, ts)
        
        entry = LedgerEntry(index, prev.entry_hash, ts, pci, entry_hash)
        self.chain.append(entry)
        logger.info(f"⛓️  Block #{index} appended. Hash: {entry_hash[:8]}...")
        return True
    
    def verify_integrity(self) -> bool:
        """Check hash chain integrity."""
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i-1]
            if curr.prev_hash != prev.entry_hash:
                logger.error(f"Integrity Fail at #{i}: Prev hash mismatch")
                return False
            recalc = self._hash_entry(curr.index, curr.prev_hash, curr.data, curr.timestamp)
            if recalc != curr.entry_hash:
                logger.error(f"Integrity Fail at #{i}: Hash mismatch")
                return False
        return True


# --- 3. The Agent (Producer of PCI) ---

class HighSecurityAgent:
    def __init__(self, agent_id: str, secret_key: bytes):
        self.agent_id = agent_id
        self.secret_key = secret_key

    def create_intent(self, amount: float, recipient: str, context_snapshot: Dict) -> Dict[str, Any]:
        """Create Proof-Carrying Intent."""
        
        # 1. Bind to Context (prevent repurposing intent in different state)
        context_hash = hash_content(context_snapshot)
        
        # 2. Construct Payload
        intent_payload = {
            "agent_id": self.agent_id,
            "dfid": new_dfid(),
            "action": "TRANSFER",
            "params": {"amount": amount, "recipient": recipient},
            "context_bind": context_hash, # Binds intent to this specific reality
            "timestamp": time.time()
        }
        
        # 3. Sign (Proof of Authorship + Integrity)
        canonical_str = json.dumps(intent_payload, sort_keys=True)
        signature = sign_data(self.secret_key, canonical_str)
        
        # 4. Attach Proof
        pci = {
            "payload": intent_payload,
            "proof": {
                "signer": self.agent_id,
                "signature": signature,
                "algo": "HMAC-SHA256"
            }
        }
        return pci


# --- 4. The Verifier (Gatekeeper) ---

class LedgertGatekeeper:
    def __init__(self, ledger: DecisionLedger, keys: Dict[str, bytes]):
        self.ledger = ledger
        self.keys = keys # Registry of public keys (secrets in this mock)

    def submit(self, pci: Dict[str, Any], context_snapshot: Dict) -> bool:
        payload = pci["payload"]
        proof = pci["proof"]
        agent_id = payload["agent_id"]
        
        # 1. Verify User
        if agent_id not in self.keys:
            logger.warning(f"⛔ REJECT: Unknown agent {agent_id}")
            return False
            
        # 2. Verify Context Binding
        current_ctx_hash = hash_content(context_snapshot)
        if payload["context_bind"] != current_ctx_hash:
            logger.warning("⛔ REJECT: Context mismatch (Stale intent or replay?)")
            return False
            
        # 3. Verify Signature
        canonical_str = json.dumps(payload, sort_keys=True)
        is_valid = verify_signature(self.keys[agent_id], canonical_str, proof["signature"])
        
        if not is_valid:
            logger.warning("⛔ REJECT: Invalid Signature")
            return False
            
        logger.info(f"✅ VERIFIED PCI from {agent_id}. Action: {payload['action']}")
        self.ledger.append(pci)
        return True


# --- 5. Simulation ---

def main():
    print("=" * 70)
    print("Decision Ledger & Proof-Carrying Intents (PCI)")
    print("=" * 70)

    # Setup
    ledger = DecisionLedger()
    agent_key = b"bank_super_secret"
    agent = HighSecurityAgent("agent_banker", agent_key)
    gatekeeper = LedgertGatekeeper(ledger, {"agent_banker": agent_key})
    
    # State A
    context_a = {"balance": 1000, "status": "active"}
    
    # Scene 1: Valid Transaction
    print("\n[Scene 1] Valid Transfer")
    pci_1 = agent.create_intent(100.0, "alice", context_a)
    gatekeeper.submit(pci_1, context_a)
    
    # Scene 2: Tampered Payload (Man-in-the-middle)
    print("\n[Scene 2] Tampered Payload")
    pci_2 = agent.create_intent(50.0, "bob", context_a)
    # Attacker changes amount
    pci_2["payload"]["params"]["amount"] = 999999.0 
    gatekeeper.submit(pci_2, context_a)
    
    # Scene 3: Replay Attack (Context Mismatch)
    print("\n[Scene 3] Replay Attack (Context Mismatch)")
    # State changes
    context_b = {"balance": 900, "status": "active"} 
    # Attacker tries to replay pci_1 (which was valid for context_a)
    gatekeeper.submit(pci_1, context_b)
    
    # Scene 4: Ledger Integrity Check
    print("\n[Scene 4] Ledger Verification")
    if ledger.verify_integrity():
        print("✅ Ledger Integrity OK")
    else:
        print("❌ Ledger Corrupted")


if __name__ == "__main__":
    main()
