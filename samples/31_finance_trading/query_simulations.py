#!/usr/bin/env python3
"""
Query simulation database - helper script for analyzing simulation results.

Usage:
  python query_simulations.py list                     # List recent simulations
  python query_simulations.py summary <simulation_id>  # Show simulation summary
  python query_simulations.py decisions <sim_id>       # Show all decisions
  python query_simulations.py prices <sim_id>          # Show price statistics
"""

import sys
from pathlib import Path
from simulation_database import SimulationDatabase


def list_simulations(db_path: Path):
    """List recent simulation runs."""
    db = SimulationDatabase(db_path)
    db.connect()
    
    simulations = db.list_simulations(limit=20)
    
    print("\n" + "="*80)
    print("Recent Simulations")
    print("="*80)
    
    for sim in simulations:
        print(f"\nSimulation ID: {sim['simulation_id']}")
        print(f"  Timestamp: {sim['run_timestamp']}")
        print(f"  Status: {sim['status']}")
        print(f"  Ticks: {sim['simulation_ticks']}")
        print(f"  Decisions: {sim['total_decisions']}")
        print(f"  Positions: {sim['total_positions']}")
        print(f"  News: {sim['total_news_events']}")
        if sim['completed_at']:
            print(f"  Completed: {sim['completed_at']}")
        if sim['error_message']:
            print(f"  Error: {sim['error_message']}")
    
    db.close()


def show_summary(db_path: Path, sim_id: str):
    """Show detailed summary for a simulation."""
    db = SimulationDatabase(db_path)
    db.connect()
    db.current_simulation_id = sim_id
    
    summary = db.get_simulation_summary(sim_id)
    if not summary:
        print(f"Simulation {sim_id} not found")
        db.close()
        return
    
    print("\n" + "="*80)
    print(f"Simulation Summary: {sim_id}")
    print("="*80)
    
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    # Query some statistics
    cursor = db.conn.cursor()
    
    # Count ticks per instrument
    cursor.execute("""
        SELECT instrument, COUNT(*) as tick_count, 
               MIN(price) as min_price, MAX(price) as max_price, AVG(price) as avg_price
        FROM ticks 
        WHERE simulation_id = ?
        GROUP BY instrument
    """, (sim_id,))
    
    print("\n" + "-"*80)
    print("Price Statistics by Instrument")
    print("-"*80)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} ticks, "
              f"min={row[2]:.2f}, max={row[3]:.2f}, avg={row[4]:.2f}")
    
    # Count decisions by policy kind
    cursor.execute("""
        SELECT policy_kind, COUNT(*) as count
        FROM decisions
        WHERE simulation_id = ?
        GROUP BY policy_kind
        ORDER BY count DESC
    """, (sim_id,))
    
    print("\n" + "-"*80)
    print("Decisions by Policy Kind")
    print("-"*80)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    db.close()


def show_decisions(db_path: Path, sim_id: str):
    """Show all decisions for a simulation."""
    db = SimulationDatabase(db_path)
    db.connect()
    
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT tick_index, agent_id, policy_kind, dim_result, instrument, price, justification
        FROM decisions
        WHERE simulation_id = ?
        ORDER BY tick_index
        LIMIT 50
    """, (sim_id,))
    
    print("\n" + "="*80)
    print(f"Decisions for {sim_id} (first 50)")
    print("="*80)
    
    for row in cursor.fetchall():
        tick, agent, policy, dim, inst, price, just = row
        just_short = (just[:60] + "...") if just and len(just) > 60 else just
        print(f"\nTick {tick}: {agent}")
        print(f"  Policy: {policy} ({dim})")
        print(f"  Instrument: {inst}, Price: {price}")
        if just_short:
            print(f"  Justification: {just_short}")
    
    db.close()


def show_prices(db_path: Path, sim_id: str):
    """Show price evolution for all instruments."""
    db = SimulationDatabase(db_path)
    db.connect()
    
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT tick_index, instrument, price, trend
        FROM ticks
        WHERE simulation_id = ?
        ORDER BY tick_index
        LIMIT 100
    """, (sim_id,))
    
    print("\n" + "="*80)
    print(f"Price Evolution for {sim_id} (first 100 ticks)")
    print("="*80)
    
    for row in cursor.fetchall():
        tick, inst, price, trend = row
        print(f"Tick {tick:3d}: {inst:10s} {price:10.2f} ({trend})")
    
    db.close()


def main():
    db_path = Path(__file__).parent / "simulation_data.db"
    
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run a simulation first: python run.py")
        return
    
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_simulations(db_path)
    elif command == "summary":
        if len(sys.argv) < 3:
            print("Usage: python query_simulations.py summary <simulation_id>")
            return
        show_summary(db_path, sys.argv[2])
    elif command == "decisions":
        if len(sys.argv) < 3:
            print("Usage: python query_simulations.py decisions <simulation_id>")
            return
        show_decisions(db_path, sys.argv[2])
    elif command == "prices":
        if len(sys.argv) < 3:
            print("Usage: python query_simulations.py prices <simulation_id>")
            return
        show_prices(db_path, sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
