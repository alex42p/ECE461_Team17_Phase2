import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import ThreadedConnectionPool
import logging
from typing import Optional, Dict, List, Any
from contextlib import contextmanager
import json

logger = logging.getLogger(__name__)

class DatabaseService:
    """Handles all db operations with connection pooling"""

    def __init__(self, db_config: Dict):
        self.db_config = db_config

        # creat connection pool
        self.pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            **db_config
        )

        logger.info("Database connection pool created")

    @contextmanager
    def get_connection(self):
        """Context manager for db connections"""

        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            self.pool.putconn(conn)

    def create_artifact(self, artifact_data: Dict) -> Dict:
        """Insert new artifact into db"""

        query = """
            INSERT INTO artifacts (
                    id, artifact_type, name, version, url, s3_key, 
                    readme_content, metadata, scores, net_score, created_by
                ) VALUES (
                    %(id)s, %(artifact_type)s, %(name)s, %(version)s, %(url)s,
                    %(s3_key)s, %(readme_content)s, %(metadata)s::jsonb,
                    %(scores)s::jsonb, %(net_score)s, %(created_by)s
                ) RETURNING *
            """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                # convert dict fields to JSON
                artifact_data['metadata'] = Json(artifact_data.get('metadata', {}))
                artifact_data['scores'] = Json(artifact_data.get('scores', {}))
                
                cur.execute(query, artifact_data)
                result = cur.fetchone()

                # log audit
                self._log_audit(conn, {
                    'artifact_id': result['id'],
                    'artifact_type': result['artifact_type'],
                    'action': 'CREATE',
                    'user_id': artifact_data.get('user_id'),
                    'details': {'name': result['name'], 'version': result['version']}
                })
                
                return dict(result)

    def get_artifact_by_id(self, artifact_id: str,
                           artifact_type: Optional[str] = None) -> Optional[Dict]:
        """Retrieve artifact by ID"""

        query = """
            SELECT * FROM artifacts 
            WHERE id = %s AND is_deleted = FALSE
        """

        params = [artifact_id]

        if artifact_type:
            query += " AND artifact_type = %s"
            params.append(artifact_type)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                cur.execute(query, params)
                result = cur.fetchone()
                
                if result:
                    # log audit
                    self._log_audit(conn, {
                        'artifact_id': artifact_id,
                        'artifact_type': artifact_type,
                        'action': 'READ',
                        'details': {'found': True}
                    })
                    
                return dict(result) if result else None
            
    def update_artifact(self, artifact_id: str, updates: Dict) -> Optional[Dict]:
        """Update artifact details"""

        # save current version to history
        current = self.get_artifact_by_id(artifact_id)
        if not current:
            return None
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                # save to version history
                version_query = """
                    INSERT INTO artifact_versions (
                        artifact_id, version_number, s3_key, metadata
                    ) VALUES (
                        %s, 
                        COALESCE((SELECT MAX(version_number) + 1 
                                 FROM artifact_versions 
                                 WHERE artifact_id = %s), 1),
                        %s, %s::jsonb
                    )
                """

                cur.execute(version_query, [
                    artifact_id, artifact_id,
                    current.get('s3_key'),
                    Json(current.get('metadata', {}))
                ])

                # update artifact
                update_parts = []
                params = []
                for key, value in updates.items():
                    if key in ['metadata', 'scores']:
                        update_parts.append(f"{key} = %s::jsonb")
                        params.append(Json(value))
                    else:
                        update_parts.append(f"{key} = %s")
                        params.append(value)
                
                update_parts.append("updated_at = CURRENT_TIMESTAMP")
                params.append(artifact_id)
                
                update_query = f"""
                    UPDATE artifacts 
                    SET {', '.join(update_parts)}
                    WHERE id = %s AND is_deleted = FALSE
                    RETURNING *
                """
                
                cur.execute(update_query, params)
                result = cur.fetchone()
                
                # log audit
                self._log_audit(conn, {
                    'artifact_id': artifact_id,
                    'action': 'UPDATE',
                    'details': {'updates': list(updates.keys())}
                })
                
                return dict(result) if result else None
            
    def soft_delete_artifact(self, artifact_id: str) -> bool:
        """Mark artifact as deleted"""

        query = """
            UPDATE artifacts 
            SET is_deleted = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, [artifact_id])
                result = cur.fetchone()
                
                if result:
                    # log audit
                    self._log_audit(conn, {
                        'artifact_id': artifact_id,
                        'action': 'DELETE',
                        'details': {'soft_delete': True}
                    })
                
                return result is not None
            
    def search_artifacts(self, filters: Dict, offset: int = 0, 
                         limit: int = 100) -> List[Dict]:
        """Search artifacts based on filters"""

        query = """
            SELECT * FROM artifacts 
            WHERE is_deleted = FALSE
        """
        params = []
        
        # build filter conditions
        conditions = []
        
        if filters.get('name'):
            conditions.append("name ILIKE %s")
            params.append(f"%{filters['name']}%")
        
        if filters.get('artifact_type'):
            conditions.append("artifact_type = %s")
            params.append(filters['artifact_type'])
        
        if filters.get('min_score'):
            conditions.append("net_score >= %s")
            params.append(filters['min_score'])
        
        if conditions:
            query += " AND " + " AND ".join(conditions)
        
        # add ordering and pagination
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                cur.execute(query, params)
                results = cur.fetchall()

                return [dict(r) for r in results]
        
    def search_by_regex(self, pattern: str, search_readme: bool = True) -> List[Dict]:
        """Search artifacts using regex pattern"""

        if search_readme:

            query = """
                SELECT * FROM artifacts 
                WHERE is_deleted = FALSE 
                AND (name ~ %s OR readme_content ~ %s)
                ORDER BY 
                    CASE 
                        WHEN name ~ %s THEN 0 
                        ELSE 1 
                    END,
                    created_at DESC
                LIMIT 100
            """
            params = [pattern, pattern, pattern]

        else:

            query = """
                SELECT * FROM artifacts 
                WHERE is_deleted = FALSE AND name ~ %s
                ORDER BY created_at DESC
                LIMIT 100
            """
            params = [pattern]

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                cur.execute(query, params)
                results = cur.fetchall()

                return [dict(r) for r in results]
            
    def get_by_name(self, name: str) -> List[Dict]:
        """Get artifacts by exact name match"""

        query = """
            SELECT * FROM artifacts 
            WHERE name = %s AND is_deleted = FALSE
            ORDER BY created_at DESC
        """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                cur.execute(query, [name])
                results = cur.fetchall()

                return [dict(r) for r in results]
            
    def reset_system(self):
        """Clear data and reset to initial state"""

        queries = [
            "TRUNCATE TABLE audit_logs CASCADE",
            "TRUNCATE TABLE lineage_relationships CASCADE",
            "TRUNCATE TABLE artifact_versions CASCADE",
            "TRUNCATE TABLE artifacts CASCADE",
            "DELETE FROM users WHERE username != 'admin'",
            """
            INSERT INTO users (username, email, password_hash, role) 
            VALUES ('admin', 'admin@registry.local', '$2b$12$defaulthash', 'admin')
            ON CONFLICT (username) DO NOTHING
            """
        ]

        with self.get_connection() as conn:
            with conn.cursor() as cur:

                for query in queries:
                    cur.execute(query)
                
                logger.info("System reset completed")

    def _log_audit(self, conn, audit_data: Dict):
        """Internal method to log audit entries"""

        query = """
            INSERT INTO audit_logs (
                artifact_id, artifact_type, user_id, action, details
            ) VALUES (%s, %s, %s, %s, %s::jsonb)
        """
        
        with conn.cursor() as cur:
            
            cur.execute(query, [
                audit_data.get('artifact_id'),
                audit_data.get('artifact_type'),
                audit_data.get('user_id'),
                audit_data['action'],
                Json(audit_data.get('details', {}))
            ])
    