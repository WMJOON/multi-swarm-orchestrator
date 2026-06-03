"""
mso-conversation-analytics — 5개 분석 함수 (DuckDB in-memory)
PCA tools/conversation/transitions.py 이식 + MSO 도메인 적용.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb

_DEFAULT_TURNS_PATH = Path("workspace/.mso-context/conversation/turns.jsonl")

# DuckDB은 JSON 배열을 VARCHAR[]로 읽을 때 버전별 차이 있음 — 명시 컬럼 지정
_COLUMNS = """{
    type:                         'VARCHAR',
    turn_id:                      'VARCHAR',
    session_id:                   'VARCHAR',
    timestamp:                    'TIMESTAMPTZ',
    utterance:                    'VARCHAR',
    resolved_intent_id:           'VARCHAR',
    resolved_target_entity_id:    'VARCHAR',
    resolved_target_concepts:     'VARCHAR[]',
    slots_filled:                 'VARCHAR',
    reprompt_count:               'INTEGER',
    success:                      'BOOLEAN',
    duration_ms:                  'INTEGER',
    prev_turn_id:                 'VARCHAR'
}"""


# ─── 로더 ─────────────────────────────────────────────────────

def load_turns(path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """
    turns.jsonl → DuckDB in-memory `turns` VIEW.
    파일 없거나 비어 있으면 빈 VIEW 반환 (exception 없음).
    """
    if path is None:
        path = os.environ.get("MSO_TURNS_PATH", str(_DEFAULT_TURNS_PATH))
    path = Path(path)
    con = duckdb.connect()

    if not path.exists() or path.stat().st_size == 0:
        # 빈 스키마로 VIEW 생성
        con.execute("""
            CREATE VIEW turns AS
            SELECT
                NULL::VARCHAR       AS type,
                NULL::VARCHAR       AS turn_id,
                NULL::VARCHAR       AS session_id,
                NULL::TIMESTAMPTZ   AS timestamp,
                NULL::VARCHAR       AS utterance,
                NULL::VARCHAR       AS resolved_intent_id,
                NULL::VARCHAR       AS resolved_target_entity_id,
                NULL::VARCHAR[]     AS resolved_target_concepts,
                NULL::VARCHAR       AS slots_filled,
                NULL::INTEGER       AS reprompt_count,
                NULL::BOOLEAN       AS success,
                NULL::INTEGER       AS duration_ms,
                NULL::VARCHAR       AS prev_turn_id
            WHERE 1=0
        """)
        return con

    con.execute(f"""
        CREATE VIEW turns AS
        SELECT * FROM read_json(
            '{path}',
            columns={_COLUMNS},
            ignore_errors=true
        )
        WHERE type = 'turn'
    """)
    return con


# ─── 5개 분석 함수 ────────────────────────────────────────────

def transition_matrix(con: duckdb.DuckDBPyConnection, days: int = 7) -> list[dict]:
    """
    intent → intent 전이 빈도 + 비율.
    Returns: [{"from_intent","to_intent","cnt","pct"}, ...]
    """
    rows = con.execute(f"""
        WITH pairs AS (
            SELECT
                prev.resolved_intent_id  AS from_intent,
                cur.resolved_intent_id   AS to_intent,
                COUNT(*)                 AS cnt
            FROM turns cur
            JOIN turns prev ON cur.prev_turn_id = prev.turn_id
            WHERE cur.success  = TRUE
              AND prev.success = TRUE
              AND cur.resolved_intent_id  IS NOT NULL
              AND prev.resolved_intent_id IS NOT NULL
              AND cur.timestamp >= NOW() - INTERVAL '{days} days'
            GROUP BY 1, 2
        ),
        totals AS (
            SELECT from_intent, SUM(cnt) AS total FROM pairs GROUP BY 1
        )
        SELECT
            p.from_intent,
            p.to_intent,
            p.cnt,
            ROUND(p.cnt * 100.0 / t.total, 1) AS pct
        FROM pairs p
        JOIN totals t USING (from_intent)
        ORDER BY p.from_intent, p.cnt DESC
    """).fetchall()
    keys = ["from_intent", "to_intent", "cnt", "pct"]
    return [dict(zip(keys, r)) for r in rows]


def factored(con: duckdb.DuckDBPyConnection, days: int = 7) -> list[dict]:
    """
    (intent × target_concept) → (intent × target_concept) 전이.
    PRD 부록 10.2 SQL 이식.
    Returns: [{"from_intent","from_target","to_intent","to_target","cnt"}, ...]
    """
    rows = con.execute(f"""
        WITH unnested AS (
            SELECT
                turn_id,
                prev_turn_id,
                resolved_intent_id,
                success,
                COALESCE(
                    UNNEST(resolved_target_concepts),
                    '_no_concept'
                ) AS target_concept
            FROM turns
            WHERE resolved_intent_id IS NOT NULL
              AND timestamp >= NOW() - INTERVAL '{days} days'
        ),
        pairs AS (
            SELECT
                prev.resolved_intent_id  AS from_intent,
                prev.target_concept      AS from_target_concept,
                cur.resolved_intent_id   AS to_intent,
                cur.target_concept       AS to_target_concept,
                COUNT(*)                 AS cnt
            FROM unnested cur
            JOIN unnested prev ON cur.prev_turn_id = prev.turn_id
            WHERE cur.success  = TRUE
              AND prev.success = TRUE
            GROUP BY 1, 2, 3, 4
        )
        SELECT * FROM pairs ORDER BY from_intent, cnt DESC
    """).fetchall()
    keys = ["from_intent", "from_target_concept", "to_intent", "to_target_concept", "cnt"]
    return [dict(zip(keys, r)) for r in rows]


def funnel(con: duckdb.DuckDBPyConnection, days: int = 7) -> list[dict]:
    """
    intent별 성공률·reprompt·latency funnel.
    Returns: [{"intent_id","total","success_cnt","success_rate",
               "avg_reprompt","avg_duration_ms"}, ...]
    """
    rows = con.execute(f"""
        SELECT
            resolved_intent_id                        AS intent_id,
            COUNT(*)                                  AS total,
            SUM(success::INTEGER)                     AS success_cnt,
            ROUND(AVG(success::INTEGER) * 100, 1)     AS success_rate,
            ROUND(AVG(reprompt_count), 2)             AS avg_reprompt,
            ROUND(AVG(duration_ms))                   AS avg_duration_ms
        FROM turns
        WHERE resolved_intent_id IS NOT NULL
          AND timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY 1
        ORDER BY total DESC
    """).fetchall()
    keys = ["intent_id","total","success_cnt","success_rate","avg_reprompt","avg_duration_ms"]
    return [dict(zip(keys, r)) for r in rows]


def reprompt_rate(con: duckdb.DuckDBPyConnection, days: int = 7) -> list[dict]:
    """
    reprompt_count 높은 intent → SlotSpec 튜닝 후보.
    Returns: [{"intent_id","avg_reprompt","max_reprompt","pct_over_1"}, ...]
    """
    rows = con.execute(f"""
        SELECT
            resolved_intent_id                AS intent_id,
            ROUND(AVG(reprompt_count), 2)     AS avg_reprompt,
            MAX(reprompt_count)               AS max_reprompt,
            ROUND(
                SUM(CASE WHEN reprompt_count >= 1 THEN 1 ELSE 0 END)
                * 100.0 / COUNT(*),
            1)                                AS pct_over_1
        FROM turns
        WHERE resolved_intent_id IS NOT NULL
          AND timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY 1
        HAVING AVG(reprompt_count) > 0
        ORDER BY avg_reprompt DESC
    """).fetchall()
    keys = ["intent_id","avg_reprompt","max_reprompt","pct_over_1"]
    return [dict(zip(keys, r)) for r in rows]


def unresolved(con: duckdb.DuckDBPyConnection, days: int = 7) -> list[dict]:
    """
    resolved_intent_id IS NULL 발화 목록 — 신규 intent 후보.
    Returns: [{"utterance","timestamp","session_id"}, ...]
    """
    rows = con.execute(f"""
        SELECT utterance, timestamp, session_id
        FROM turns
        WHERE resolved_intent_id IS NULL
          AND timestamp >= NOW() - INTERVAL '{days} days'
        ORDER BY timestamp DESC
    """).fetchall()
    keys = ["utterance","timestamp","session_id"]
    return [dict(zip(keys, r)) for r in rows]
