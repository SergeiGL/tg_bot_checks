import asyncio
from typing import Optional, Tuple
import psycopg
import config
import google_sheets
import time


class AsyncDatabase:    
    def __init__(self, pg_conn):
        self.pg_conn = pg_conn
        self._background_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        # Optimized cache with timestamp
        self._sheet_cache = None
        self._cache_timestamp = 0
        self._cache_ttl = config.TTL
    
    @classmethod
    async def create(cls):
        """Create database instance with connection and setup"""
        pg_conn = await psycopg.AsyncConnection.connect(
            host=config.pg_conf_keys["host"],
            dbname=config.pg_conf_keys["dbname"],
            user=config.pg_conf_keys["user"],
            password=config.pg_conf_keys["password"],
            port=config.pg_conf_keys["port"],
            prepare_threshold=5,
        )
        
        db = cls(pg_conn)
        await db._setup()
        db.start_googlesheets_sync()
        return db
    
    async def _setup(self):
        """Initialize database tables with optimized schema"""
        await self.pg_conn.set_autocommit(True)
        
        async with self.pg_conn.cursor() as cursor:
            # Create tables and indexes in a single batch
            await cursor.execute("""
                -- Create tables
                CREATE TABLE IF NOT EXISTS checks (
                    chat_id BIGINT NOT NULL PRIMARY KEY,
                    username VARCHAR(100) NOT NULL,
                    count INT NOT NULL,
                    total_people INT NOT NULL,
                    sum_to_pay INT NOT NULL,
                    check_link VARCHAR(300),
                    check_file_id VARCHAR(300),
                    first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    check_received_at TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS google_sheet_data (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    total_people INT NOT NULL,
                    total_sum BIGINT NOT NULL,
                    people_usernames TEXT[] NOT NULL,
                    paid_usernames TEXT[] NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT single_row CHECK (id = 1)
                );
                
                -- Create indexes
                CREATE INDEX IF NOT EXISTS idx_checks_username ON checks(username);
                CREATE INDEX IF NOT EXISTS idx_checks_chat_id ON checks(chat_id);
                
                -- Initialize with default data
                INSERT INTO google_sheet_data (total_people, total_sum, people_usernames)
                VALUES (0, 0, '{}')
                ON CONFLICT (id) DO NOTHING;
            """)
    
    def start_googlesheets_sync(self):
        """Start background Google Sheets synchronization"""
        if self._background_task and not self._background_task.done():
            print("Background sync already running")
            return
        
        self._stop_event.clear()
        self._background_task = asyncio.create_task(self._sync_google_sheets())
        print("Started background Google Sheets sync")
    
    async def stop_background_sync(self, timeout: float = 10.0):
        """Stop background synchronization gracefully"""
        if not self._background_task or self._background_task.done():
            return
        
        print("Stopping background sync...")
        self._stop_event.set()
        
        try:
            await asyncio.wait_for(self._background_task, timeout=timeout)
        except asyncio.TimeoutError:
            print("Background sync didn't stop gracefully, cancelling...")
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        
        print("Background sync stopped")
    
    async def _sync_google_sheets(self):
        """Background task to sync Google Sheets data - optimized"""
        print("Google Sheets sync started...")
        prev_data_hash = None
        
        try:
            while not self._stop_event.is_set():
                try:
                    google_sheet_data = await google_sheets.fetch_list()
                    
                    if google_sheet_data and self._is_valid_sheet_data(google_sheet_data):
                        current_hash = hash(str(google_sheet_data))
                        
                        if prev_data_hash != current_hash:
                            await self._update_sheet_data(google_sheet_data)
                            prev_data_hash = current_hash
                            # Update cache with current time
                            self._sheet_cache = google_sheet_data
                            self._cache_timestamp = time.time()
                            print("Google Sheets data updated")
                    
                    # Efficient sleep with cancellation
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(), 
                            timeout=config.TTL
                        )
                        break
                    except asyncio.TimeoutError:
                        continue
                        
                except Exception as e:
                    print(f"Error in Google Sheets sync: {e}")
                    await asyncio.sleep(min(60, 5 * 2**min(3, getattr(self, '_error_count', 0))))
                    
        finally:
            print("Google Sheets sync cleanup completed")
    
    def _is_valid_sheet_data(self, data: dict) -> bool:
        """Validate Google Sheets data - optimized"""
        return (
            isinstance(data, dict) and
            data.get("column_A_list") is not None and
            isinstance(data.get("total_people"), int) and
            isinstance(data.get("total_sum"), int)
        )
    
    async def _update_sheet_data(self, data: dict):
        """Update Google Sheets data - single atomic operation"""
        async with self.pg_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE google_sheet_data 
                SET total_people = %s, 
                    total_sum = %s, 
                    people_usernames = %s,
                    updated_at = NOW()
                WHERE id = 1
                """,
                (data["total_people"], data["total_sum"], data["column_A_list"])
            )
    
    async def _get_cached_sheet_data(self):
        """Get sheet data from cache or database"""
        current_time = time.time()
        
        # Use cache if fresh
        if (self._sheet_cache and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._sheet_cache
        
        # Fetch from database
        async with self.pg_conn.cursor() as cursor:
            await cursor.execute(
                "SELECT total_people, total_sum, people_usernames, paid_usernames FROM google_sheet_data WHERE id = 1"
            )
            row = await cursor.fetchone()
            
            if row:
                sheet_data = {
                    "total_people": row[0],
                    "total_sum": row[1],
                    "column_A_list": row[2],
                    "paid_usernames": row[3]
                }
                # Update cache
                self._sheet_cache = sheet_data
                self._cache_timestamp = current_time
                return sheet_data
        
        return None
    
    async def get_user_data(self, chat_id: int, username: str) -> Tuple[int, int, int, int, Optional[bool]]:
        """
        Get user values and payment status - heavily optimized.
        
        Returns:
            Tuple[int, int, int, int, Optional[bool]]: 
            (sum_to_pay, count, total_people, total_sum, paid)
        """
        sheet_data = await self._get_cached_sheet_data()
        if not sheet_data:
            raise ValueError("Unable to fetch sheet data")
        
        total_people = sheet_data["total_people"]
        total_sum = sheet_data["total_sum"]
        paid_usernames = sheet_data.get("paid_usernames", [])
        paid = username in paid_usernames if username in sheet_data["column_A_list"] else None
        
        # User is not in the column_A_list
        if paid is None:
            return None, None, None, None, None
        
        async with self.pg_conn.cursor() as cursor:
            await cursor.execute(
                "SELECT count, sum_to_pay, total_people FROM checks WHERE chat_id = %s",
                (chat_id,)
            )
            
            existing = await cursor.fetchone()
            
            if existing:
                return existing[1], existing[0], total_people, total_sum, paid
            
            # User doesn't exist, create new entry
            await cursor.execute("SELECT COALESCE(MAX(count), -1) + 1 FROM checks")
            count = (await cursor.fetchone())[0]
            
            # Calculate sum_to_pay
            if total_people > 0 and config.GEOM_SEQ_R != 1:
                geom_seq_a = total_sum * (1 - config.GEOM_SEQ_R) / (1 - config.GEOM_SEQ_R ** total_people)
                sum_to_pay = int(geom_seq_a * (config.GEOM_SEQ_R ** count) + 0.5)  # Round to nearest int
            else:
                sum_to_pay = total_sum // max(total_people, 1)
            
            # Insert new user
            await cursor.execute(
                """
                INSERT INTO checks (chat_id, username, count, total_people, sum_to_pay)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (chat_id, username, count, total_people, sum_to_pay)
            )
            
            return sum_to_pay, count, total_people, total_sum, paid
    
    async def insert_check_link(self, chat_id: int, username: str, check_link: str, check_file_id: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        """Insert check link and return user data - optimized with single transaction"""
        async with self.pg_conn.cursor() as cursor:
            # Single transaction combining both operations
            await cursor.execute(
                """
                WITH updated_payment AS (
                    UPDATE google_sheet_data
                    SET paid_usernames = CASE 
                        WHEN NOT (%s = ANY(paid_usernames)) THEN
                            array_append(paid_usernames, %s)
                        ELSE paid_usernames
                    END
                    WHERE id = 1
                    RETURNING 1
                ),
                updated_check AS (
                    UPDATE checks
                    SET check_link = %s, check_file_id = %s, check_received_at = NOW()
                    WHERE chat_id = %s
                    RETURNING count, sum_to_pay, EXTRACT(EPOCH FROM (NOW() - first_seen_at))
                )
                SELECT count, sum_to_pay, MAKE_INTERVAL(secs => EXTRACT(EPOCH FROM INTERVAL '1 second' * elapsed))
                FROM updated_check uc, (SELECT EXTRACT(EPOCH FROM (NOW() - first_seen_at)) as elapsed FROM checks WHERE chat_id = %s) e;
                """,
                (username, username, check_link, check_file_id, chat_id, chat_id)
            )
            
            result = await cursor.fetchone()
            if result is None:
                return None, None, None
            
            # Invalidate cache since paid_usernames changed
            self._cache_timestamp = 0
            
            return result[0], result[1], str(result[2])
        
    async def close(self):
        """Close database connection and stop background tasks"""
        await self.stop_background_sync()
        await self.pg_conn.close()
    
    def is_sync_running(self) -> bool:
        """Check if background sync is running"""
        return self._background_task is not None and not self._background_task.done()