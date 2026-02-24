#!/usr/bin/env python3
"""
Query position audit views - simplified access to full audit trail.

Uses database views for clean, maintainable queries.
"""

import sqlite3
import sys
from pathlib import Path
from typing import Optional


def query_aggregated_view(db_path: str, simulation_id: Optional[str] = None) -> None:
    """
    Query position_audit_aggregated view - one row per position with summary.
    
    Args:
        db_path: Path to simulation_data.db
        simulation_id: Optional simulation ID filter
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if simulation_id:
        query = "SELECT * FROM position_audit_aggregated WHERE simulation_id = ? ORDER BY entry_tick, position_id"
        cursor.execute(query, (simulation_id,))
    else:
        query = "SELECT * FROM position_audit_aggregated ORDER BY simulation_id, entry_tick, position_id"
        cursor.execute(query)
    
    rows = cursor.fetchall()
    
    if not rows:
        print(f"No positions found" + (f" for simulation_id: {simulation_id}" if simulation_id else ""))
        conn.close()
        return
    
    print(f"\n{'═'*100}")
    print(f"  POSITION LIFECYCLE REPORT")
    if simulation_id:
        print(f"  Simulation: {simulation_id}")
    print(f"{'═'*100}\n")
    
    for row in rows:
        # Header
        status_emoji = "✅" if row['close_tick'] is not None else "⏳"
        status_text = "CLOSED" if row['close_tick'] is not None else "OPEN"
        print(f"┌{'─'*98}┐")
        print(f"│ {status_emoji} Position: {row['position_id']:<20} Instrument: {row['instrument']:<15} Status: {status_text:<10} │")
        print(f"├{'─'*98}┤")
        
        # Opening details
        print(f"│ 📈 POSITION OPENED                                                                             │")
        print(f"│    Tick: {row['entry_tick']:<5} Price: ${row['entry_price']:>10.2f}                                                        │")
        print(f"│    Exposure: ${row['initial_exposure']:>8.2f}   Quantity: {row['quantity']:.6f}                                           │")
        
        # News trigger
        if row['news_full_headline']:
            headline = row['news_full_headline'][:70] + "..." if len(row['news_full_headline']) > 70 else row['news_full_headline']
            news_score = row['news_score'] if row['news_score'] is not None else 0.0
            print(f"│                                                                                                  │")
            print(f"│ 📰 NEWS TRIGGER                                                                                  │")
            print(f"│    \"{headline}\"")
            print(f"│    Sentiment: {row['news_sentiment'] or 'n/a':<12}   News Score: {news_score:.2f}                                        │")
        
        # Lifecycle events
        if row['decisions_timeline']:
            print(f"│                                                                                                  │")
            print(f"│ 📊 LIFECYCLE EVENTS                                                                              │")
            events = row['decisions_timeline'].split('\n')
            for event in events[:10]:  # Limit to 10 events
                if event.strip():
                    print(f"│    {event:<94} │")
            if len(events) > 10:
                print(f"│    ... and {len(events) - 10} more events                                                               │")
        
        # Closing details
        if row['close_tick'] is not None:
            print(f"│                                                                                                  │")
            print(f"│ 🏁 POSITION CLOSED                                                                               │")
            print(f"│    Tick: {row['close_tick']:<5} Price: ${row['close_price']:>10.2f}   Reason: {row['close_reason']:<20}             │")
            if row['pnl_percent'] is not None:
                pnl_usd = row['pnl_usd'] if row['pnl_usd'] is not None else 0.0
                pnl_color = "+" if row['pnl_percent'] >= 0 else ""
                print(f"│    P&L: {pnl_color}{row['pnl_percent']:.2f}%  (${pnl_usd:+.2f} USD)                                                           │")
        else:
            print(f"│                                                                                                  │")
            print(f"│ ⏳ POSITION STILL OPEN                                                                           │")
            print(f"│    Decisions so far: {row['total_decisions']}                                                                         │")
        
        # Summary
        print(f"│                                                                                                  │")
        print(f"│ 📋 SUMMARY: {row['total_decisions']} decisions (HOLD: {row['hold_count']}, REDUCE: {row['reduce_count']}, CLOSE: {row['close_count']})                                        │")
        if row['min_price'] and row['max_price']:
            print(f"│    Price range: ${row['min_price']:.2f} - ${row['max_price']:.2f}                                                          │")
        
        print(f"└{'─'*98}┘")
        print()
    
    conn.close()


def query_detailed_view(db_path: str, simulation_id: Optional[str] = None) -> None:
    """
    Query position_audit_detailed view - one row per decision with full details.
    
    Args:
        db_path: Path to simulation_data.db
        simulation_id: Optional simulation ID filter
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if simulation_id:
        query = "SELECT * FROM position_audit_detailed WHERE simulation_id = ? ORDER BY entry_tick, position_id, decision_tick"
        cursor.execute(query, (simulation_id,))
    else:
        query = "SELECT * FROM position_audit_detailed ORDER BY simulation_id, entry_tick, position_id, decision_tick"
        cursor.execute(query)
    
    rows = cursor.fetchall()
    
    if not rows:
        print(f"No positions found" + (f" for simulation_id: {simulation_id}" if simulation_id else ""))
        conn.close()
        return
    
    print(f"\n{'='*120}")
    print(f"POSITION AUDIT - DETAILED VIEW")
    if simulation_id:
        print(f"Simulation: {simulation_id}")
    print(f"{'='*120}\n")
    
    current_position = None
    for row in rows:
        # Print position header when we encounter a new position
        if row['position_id'] != current_position:
            if current_position:
                print(f"{'-'*120}\n")
            
            current_position = row['position_id']
            print(f"Simulation: {row['simulation_id']}")
            print(f"Position ID: {row['position_id']}")
            print(f"  Instrument: {row['instrument']}")
            print(f"  Entry: Tick {row['entry_tick']}, Price ${row['entry_price']:.2f}")
            print(f"  Exposure: Initial=${row['initial_exposure']:.2f}, Quantity={row['quantity']:.6f}")
            
            if row['close_tick'] is not None:
                print(f"  ❌ CLOSED: Tick {row['close_tick']}, Price ${row['close_price']:.2f}, Reason: {row['close_reason']}")
            
            if row['news_headline']:
                print(f"\n  📰 NEWS TRIGGER:")
                print(f"     Headline: {row['news_headline']}")
                print(f"     Sentiment: {row['news_sentiment']}, Score: {row['news_score']:.2f}")
                print(f"     Agent: {row['news_agent']}")
                if row['news_justification']:
                    print(f"     Justification: {row['news_justification'][:100]}...")
            
            print(f"\n  📍 DECISIONS:")
        
        # Print individual decision
        if row['decision_tick']:
            pnl_usd = row['pnl_usd'] if row['pnl_usd'] is not None else 0.0
            print(f"\n     Tick {row['decision_tick']}: {row['decision_type']} @ ${row['decision_price']:.2f} (P&L: {row['pnl_percent']:+.2f}% / ${pnl_usd:+.2f})")
            if row['decision_justification']:
                # Indent justification
                just_lines = row['decision_justification'].split('\n')
                for line in just_lines[:3]:  # First 3 lines only
                    print(f"        {line}")
                if len(just_lines) > 3:
                    print(f"        ...")
    
    print(f"\n{'-'*120}\n")
    conn.close()


def list_simulations(db_path: str) -> None:
    """List all simulations in database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT simulation_id, run_timestamp, status, simulation_ticks, 
               total_positions, total_decisions, total_news_events
        FROM simulations
        ORDER BY run_timestamp DESC
        LIMIT 10
    """)
    
    rows = cursor.fetchall()
    if not rows:
        print("No simulations found")
        conn.close()
        return
    
    print(f"\n{'='*120}")
    print("RECENT SIMULATIONS")
    print(f"{'='*120}\n")
    
    for row in rows:
        print(f"ID: {row['simulation_id']}")
        print(f"  Timestamp: {row['run_timestamp']}")
        print(f"  Status: {row['status']}")
        print(f"  Ticks: {row['simulation_ticks']}, Positions: {row['total_positions']}, Decisions: {row['total_decisions']}, News: {row['total_news_events']}")
        print()
    
    conn.close()


if __name__ == "__main__":
    sample_dir = Path(__file__).resolve().parent
    db_path = sample_dir / "data" / "simulation_data.db"
    
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run a simulation first to create the database.")
        sys.exit(1)
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python query_position_views.py list                    # List all simulations")
        print("  python query_position_views.py <simulation_id>         # Aggregated view for one simulation")
        print("  python query_position_views.py <simulation_id> --detailed  # Detailed view for one simulation")
        print("  python query_position_views.py all                     # Aggregated view for all simulations")
        print("  python query_position_views.py all --detailed          # Detailed view for all simulations")
        sys.exit(1)
    
    command = sys.argv[1]
    detailed = "--detailed" in sys.argv
    
    if command == "list":
        list_simulations(str(db_path))
    elif command == "all":
        if detailed:
            query_detailed_view(str(db_path))
        else:
            query_aggregated_view(str(db_path))
    else:
        simulation_id = command
        if detailed:
            query_detailed_view(str(db_path), simulation_id)
        else:
            query_aggregated_view(str(db_path), simulation_id)
