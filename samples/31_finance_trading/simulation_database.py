"""
SQLite database for simulation recording.

Creates and manages the database schema for storing simulation runs,
market ticks, agent decisions, positions, and news events.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SimulationDatabase:
    """SQLite database manager for simulation recording."""

    def __init__(self, db_path: str | Path = "simulation_data.db"):
        """Initialize database connection and ensure schema exists."""
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self.current_simulation_id: Optional[str] = None
        
    def connect(self) -> None:
        """Connect to database and initialize schema if needed."""
        is_new = not self.db_path.exists()
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        
        if is_new:
            self._create_schema()
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def _create_schema(self) -> None:
        """Create database schema (tables) on first run."""
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        cursor = self.conn.cursor()
        
        # Simulations - header record for each simulation run
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulations (
                simulation_id TEXT PRIMARY KEY,
                run_timestamp TEXT NOT NULL,
                config_hash TEXT,
                simulation_ticks INTEGER,
                total_decisions INTEGER DEFAULT 0,
                total_positions INTEGER DEFAULT 0,
                total_news_events INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                completed_at TEXT,
                error_message TEXT
            )
        """)
        
        # Ticks - market observations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id TEXT NOT NULL,
                tick_index INTEGER NOT NULL,
                instrument TEXT NOT NULL,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                dfid TEXT NOT NULL,
                trend TEXT DEFAULT 'neutral',
                volatility REAL DEFAULT 0.0,
                FOREIGN KEY (simulation_id) REFERENCES simulations(simulation_id)
            )
        """)
        
        # Decisions - agent proposals and DIM results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id TEXT NOT NULL,
                tick_index INTEGER NOT NULL,
                dfid TEXT NOT NULL,
                parent_dfid TEXT,
                agent_id TEXT NOT NULL,
                policy_kind TEXT NOT NULL,
                justification TEXT,
                dim_result TEXT NOT NULL,
                dim_reason TEXT NOT NULL,
                explain_narrative TEXT,
                explain_signals TEXT,
                explain_risks TEXT,
                explain_opportunities TEXT,
                instrument TEXT,
                price REAL,
                event_type TEXT NOT NULL,
                instruments_affected TEXT,
                FOREIGN KEY (simulation_id) REFERENCES simulations(simulation_id)
            )
        """)
        
        # Positions - spawned position/instrument manager agents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                instrument TEXT NOT NULL,
                entry_tick INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                initial_exposure REAL NOT NULL,
                current_exposure REAL NOT NULL,
                quantity REAL NOT NULL,
                parent_dfid TEXT,
                news_headline TEXT,
                close_tick INTEGER,
                close_price REAL,
                close_reason TEXT,
                FOREIGN KEY (simulation_id) REFERENCES simulations(simulation_id)
            )
        """)
        
        # Position lifecycle events - decisions by position agents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_lifecycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                tick_index INTEGER NOT NULL,
                policy_kind TEXT NOT NULL,
                price REAL NOT NULL,
                justification TEXT,
                FOREIGN KEY (simulation_id) REFERENCES simulations(simulation_id)
            )
        """)
        
        # News events
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id TEXT NOT NULL,
                dfid TEXT NOT NULL,
                headline TEXT NOT NULL,
                sentiment TEXT,
                instruments_affected TEXT,
                raw_score REAL,
                FOREIGN KEY (simulation_id) REFERENCES simulations(simulation_id)
            )
        """)
        
        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticks_sim ON ticks(simulation_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticks_instrument ON ticks(instrument)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_sim ON decisions(simulation_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_dfid ON decisions(dfid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_sim ON positions(simulation_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_sim ON position_lifecycle_events(simulation_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_sim ON news_events(simulation_id)")
        
        # Create views for position audit trail
        
        # View 1: Aggregated position audit (one row per position)
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS position_audit_agg_v AS
            WITH position_details AS (
                SELECT 
                    p.simulation_id,
                    p.position_id,
                    p.instrument,
                    p.entry_tick,
                    p.entry_price,
                    p.initial_exposure,
                    p.current_exposure,
                    p.quantity,
                    p.close_tick,
                    p.close_price,
                    p.close_reason,
                    p.parent_dfid,
                    p.news_headline,
                    n.headline AS news_full_headline,
                    n.sentiment AS news_sentiment,
                    n.raw_score AS news_score,
                    d_news.agent_id AS news_agent,
                    d_news.justification AS news_justification
                FROM positions p
                LEFT JOIN news_events n ON p.parent_dfid = n.dfid AND p.simulation_id = n.simulation_id
                LEFT JOIN decisions d_news ON p.parent_dfid = d_news.dfid 
                                           AND d_news.policy_kind = 'NEWS_QUALIFIED'
                                           AND p.simulation_id = d_news.simulation_id
            )
            SELECT 
                pd.simulation_id,
                pd.position_id,
                pd.instrument,
                pd.entry_tick,
                pd.entry_price,
                pd.initial_exposure,
                pd.quantity,
                pd.close_tick,
                pd.close_price,
                pd.close_reason,
                pd.news_full_headline,
                pd.news_sentiment,
                pd.news_score,
                pd.news_agent,
                pd.news_justification,
                COUNT(ple.id) AS total_decisions,
                GROUP_CONCAT(
                    'T' || ple.tick_index || ': ' || ple.policy_kind || ' @$' || ROUND(ple.price, 2),
                    CHAR(10)
                ) AS decisions_timeline,
                MIN(ple.price) AS min_price,
                MAX(ple.price) AS max_price,
                AVG(ple.price) AS avg_price,
                SUM(CASE WHEN ple.policy_kind = 'HOLD' THEN 1 ELSE 0 END) AS hold_count,
                SUM(CASE WHEN ple.policy_kind = 'REDUCE' THEN 1 ELSE 0 END) AS reduce_count,
                SUM(CASE WHEN ple.policy_kind = 'CLOSE' THEN 1 ELSE 0 END) AS close_count,
                CASE 
                    WHEN pd.close_price IS NOT NULL
                    THEN ROUND(
                        (pd.close_price - pd.entry_price) / pd.entry_price * 100, 
                        2
                    )
                    ELSE NULL
                END AS pnl_percent,
                CASE 
                    WHEN pd.close_price IS NOT NULL
                    THEN ROUND(
                        pd.quantity * (pd.close_price - pd.entry_price), 
                        2
                    )
                    ELSE NULL
                END AS pnl_usd
            FROM position_details pd
            LEFT JOIN position_lifecycle_events ple ON pd.position_id = ple.position_id
             AND pd.simulation_id = ple.simulation_id
            GROUP BY 
                pd.simulation_id,
                pd.position_id, 
                pd.instrument, 
                pd.entry_tick, 
                pd.entry_price,
                pd.initial_exposure,
                pd.quantity,
                pd.close_tick,
                pd.close_price,
                pd.close_reason,
                pd.news_full_headline,
                pd.news_sentiment,
                pd.news_score,
                pd.news_agent,
                pd.news_justification
            ORDER BY pd.simulation_id, pd.entry_tick, pd.position_id
        """)
        
        # View 2: Detailed position audit (one row per decision)
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS position_audit_det_v AS
            SELECT 
                p.simulation_id,
                p.position_id,
                p.instrument,
                p.entry_tick,
                p.entry_price,
                p.initial_exposure,
                p.quantity,
                p.close_tick,
                p.close_price,
                p.close_reason,
                n.headline AS news_headline,
                n.sentiment AS news_sentiment,
                n.raw_score AS news_score,
                d_news.agent_id AS news_agent,
                d_news.justification AS news_justification,
                ple.tick_index AS decision_tick,
                ple.policy_kind AS decision_type,
                ple.price AS decision_price,
                ple.justification AS decision_justification,
                ROUND((ple.price - p.entry_price) / p.entry_price * 100, 2) AS pnl_percent,
                ROUND(p.quantity * (ple.price - p.entry_price), 2) AS pnl_usd
            FROM positions p
            LEFT JOIN news_events n ON p.parent_dfid = n.dfid AND p.simulation_id = n.simulation_id
            LEFT JOIN decisions d_news ON p.parent_dfid = d_news.dfid 
                                       AND d_news.policy_kind = 'NEWS_QUALIFIED'
                                       AND p.simulation_id = d_news.simulation_id
            LEFT JOIN position_lifecycle_events ple ON p.position_id = ple.position_id
            ORDER BY p.simulation_id, p.entry_tick, p.position_id, ple.tick_index
        """)
        
        self.conn.commit()
    
    def start_simulation(self, config: Dict[str, Any]) -> str:
        """
        Create a new simulation header record.
        
        Args:
            config: Simulation configuration dict
            
        Returns:
            simulation_id (unique hash)
        """
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        # Generate simulation ID from timestamp and config
        timestamp = datetime.now(timezone.utc).isoformat()
        config_str = json.dumps(config, sort_keys=True)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
        
        # Simulation ID: timestamp + config hash (first 8 chars)
        sim_id = f"sim_{timestamp.replace(':', '-').replace('.', '-')}_{config_hash[:8]}"
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO simulations 
            (simulation_id, run_timestamp, config_hash, simulation_ticks, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (sim_id, timestamp, config_hash, config.get("simulation", {}).get("simulation_ticks"))
        )
        self.conn.commit()
        
        self.current_simulation_id = sim_id
        return sim_id
    
    def complete_simulation(self, status: str = "completed", error_message: Optional[str] = None) -> None:
        """Mark simulation as completed or failed."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE simulations 
            SET status = ?, 
                completed_at = ?,
                error_message = ?,
                total_decisions = (SELECT COUNT(*) FROM decisions WHERE simulation_id = ?),
                total_positions = (SELECT COUNT(*) FROM positions WHERE simulation_id = ?),
                total_news_events = (SELECT COUNT(*) FROM news_events WHERE simulation_id = ?)
            WHERE simulation_id = ?
            """,
            (
                status,
                datetime.now(timezone.utc).isoformat(),
                error_message,
                self.current_simulation_id,
                self.current_simulation_id,
                self.current_simulation_id,
                self.current_simulation_id,
            )
        )
        self.conn.commit()
    
    def insert_tick(
        self,
        tick_index: int,
        instrument: str,
        price: float,
        timestamp: str,
        dfid: str,
        trend: str = "neutral",
        volatility: float = 0.0,
    ) -> None:
        """Insert a market tick record."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO ticks 
            (simulation_id, tick_index, instrument, price, timestamp, dfid, trend, volatility)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.current_simulation_id, tick_index, instrument, price, timestamp, dfid, trend, volatility)
        )
        self.conn.commit()
    
    def insert_decision(
        self,
        tick_index: int,
        dfid: str,
        parent_dfid: Optional[str],
        agent_id: str,
        policy_kind: str,
        justification: Optional[str],
        dim_result: str,
        dim_reason: str,
        explain_narrative: Optional[str],
        explain_signals: List[str],
        explain_risks: List[str],
        explain_opportunities: List[str],
        instrument: Optional[str],
        price: Optional[float],
        event_type: str,
        instruments_affected: List[str],
    ) -> None:
        """Insert a decision record."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO decisions 
            (simulation_id, tick_index, dfid, parent_dfid, agent_id, policy_kind, justification,
             dim_result, dim_reason, explain_narrative, explain_signals, explain_risks, 
             explain_opportunities, instrument, price, event_type, instruments_affected)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.current_simulation_id, tick_index, dfid, parent_dfid, agent_id, policy_kind,
                justification, dim_result, dim_reason, explain_narrative,
                json.dumps(explain_signals), json.dumps(explain_risks), json.dumps(explain_opportunities),
                instrument, price, event_type, json.dumps(instruments_affected)
            )
        )
        self.conn.commit()
    
    def insert_position(
        self,
        position_id: str,
        instrument: str,
        entry_tick: int,
        entry_price: float,
        initial_exposure: float,
        quantity: float,
        parent_dfid: Optional[str] = None,
        news_headline: Optional[str] = None,
    ) -> None:
        """Insert a position spawn record with exposure tracking."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO positions 
            (simulation_id, position_id, instrument, entry_tick, entry_price, 
             initial_exposure, current_exposure, quantity, parent_dfid, news_headline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.current_simulation_id, position_id, instrument, entry_tick, entry_price,
             initial_exposure, initial_exposure, quantity, parent_dfid, news_headline)
        )
        self.conn.commit()
    
    def close_position(
        self,
        position_id: str,
        close_tick: int,
        close_price: float,
        close_reason: str,
    ) -> None:
        """Update position with closure information."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE positions
            SET close_tick = ?, close_price = ?, close_reason = ?, current_exposure = 0.0
            WHERE simulation_id = ? AND position_id = ?
            """,
            (close_tick, close_price, close_reason, self.current_simulation_id, position_id)
        )
        self.conn.commit()
    
    def update_position_exposure(
        self,
        position_id: str,
        new_exposure: float,
    ) -> None:
        """Update current_exposure for a position (after REDUCE)."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE positions
            SET current_exposure = ?
            WHERE simulation_id = ? AND position_id = ?
            """,
            (new_exposure, self.current_simulation_id, position_id)
        )
        self.conn.commit()
    
    def insert_position_lifecycle_event(
        self,
        position_id: str,
        tick_index: int,
        policy_kind: str,
        price: float,
        justification: Optional[str] = None,
    ) -> None:
        """Insert a position lifecycle event."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO position_lifecycle_events 
            (simulation_id, position_id, tick_index, policy_kind, price, justification)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (self.current_simulation_id, position_id, tick_index, policy_kind, price, justification)
        )
        self.conn.commit()
    
    def insert_news_event(
        self,
        dfid: str,
        headline: str,
        sentiment: Optional[str],
        instruments_affected: List[str],
        raw_score: Optional[float],
    ) -> None:
        """Insert a news event record."""
        if not self.conn or not self.current_simulation_id:
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO news_events 
            (simulation_id, dfid, headline, sentiment, instruments_affected, raw_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (self.current_simulation_id, dfid, headline, sentiment, json.dumps(instruments_affected), raw_score)
        )
        self.conn.commit()
    
    def get_simulation_summary(self, simulation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get summary for a simulation run."""
        if not self.conn:
            return None
        
        sim_id = simulation_id or self.current_simulation_id
        if not sim_id:
            return None
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM simulations WHERE simulation_id = ?", (sim_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def list_simulations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent simulation runs."""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM simulations 
            ORDER BY run_timestamp DESC 
            LIMIT ?
            """,
            (limit,)
        )
        
        return [dict(row) for row in cursor.fetchall()]
    
    def load_ticks(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load all ticks for a simulation."""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT tick_index, instrument, price, timestamp, dfid, trend, volatility
            FROM ticks
            WHERE simulation_id = ?
            ORDER BY tick_index
            """,
            (simulation_id,)
        )
        
        return [dict(row) for row in cursor.fetchall()]
    
    def load_decisions(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load all decisions for a simulation."""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT tick_index, dfid, parent_dfid, agent_id, policy_kind, justification,
                   dim_result, dim_reason, explain_narrative, explain_signals, 
                   explain_risks, explain_opportunities, instrument, price, event_type,
                   instruments_affected
            FROM decisions
            WHERE simulation_id = ?
            ORDER BY tick_index
            """,
            (simulation_id,)
        )
        
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            # Parse JSON fields
            if d.get('explain_signals'):
                d['explain_signals'] = json.loads(d['explain_signals']) if d['explain_signals'] else []
            else:
                d['explain_signals'] = []
            if d.get('explain_risks'):
                d['explain_risks'] = json.loads(d['explain_risks']) if d['explain_risks'] else []
            else:
                d['explain_risks'] = []
            if d.get('explain_opportunities'):
                d['explain_opportunities'] = json.loads(d['explain_opportunities']) if d['explain_opportunities'] else []
            else:
                d['explain_opportunities'] = []
            if d.get('instruments_affected'):
                d['instruments_affected'] = json.loads(d['instruments_affected']) if d['instruments_affected'] else []
            else:
                d['instruments_affected'] = []
            rows.append(d)
        
        return rows
    
    def load_positions(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load all positions with their lifecycle events for a simulation."""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        
        # Load positions
        cursor.execute(
            """
            SELECT position_id, instrument, entry_tick, entry_price, 
                   initial_exposure, current_exposure, quantity, parent_dfid, 
                   news_headline, close_tick, close_price, close_reason
            FROM positions
            WHERE simulation_id = ?
            ORDER BY entry_tick
            """,
            (simulation_id,)
        )
        
        positions = []
        for row in cursor.fetchall():
            pos = dict(row)
            
            # Load lifecycle events for this position
            cursor.execute(
                """
                SELECT tick_index, policy_kind, price, justification
                FROM position_lifecycle_events
                WHERE simulation_id = ? AND position_id = ?
                ORDER BY tick_index
                """,
                (simulation_id, pos['position_id'])
            )
            
            pos['lifecycle_events'] = [dict(e) for e in cursor.fetchall()]
            positions.append(pos)
        
        return positions
    
    def load_news_events(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load all news events for a simulation."""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT dfid, headline, sentiment, instruments_affected, raw_score
            FROM news_events
            WHERE simulation_id = ?
            ORDER BY id
            """,
            (simulation_id,)
        )
        
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            # Parse JSON field
            if d.get('instruments_affected'):
                d['instruments_affected'] = json.loads(d['instruments_affected']) if d['instruments_affected'] else []
            else:
                d['instruments_affected'] = []
            rows.append(d)
        
        return rows
