import psycopg
import config


class AsyncDatabase:
    def __init__(self, pg_conn):
        # Synchronous __init__—no awaits here.
        self.pg_conn = pg_conn

    @classmethod
    async def create(cls):
        """
        Async “constructor”:
        1. open the connection
        2. call the synchronous __init__
        3. run any setup/DDL
        4. return the instance
        """
        pg_conn = await psycopg.AsyncConnection.connect(
            host=config.pg_conf_keys["host"],
            dbname=config.pg_conf_keys["dbname"],
            user=config.pg_conf_keys["user"],
            password=config.pg_conf_keys["password"],
            port=config.pg_conf_keys["port"],
        )
        db = cls(pg_conn)
        await db._setup()
        return db

    async def _setup(self):
        await self.pg_conn.set_autocommit(True)
        async with self.pg_conn.cursor() as cursor:
            if config.is_drop_all_tables:
                await cursor.execute("""
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public';
                """)
                tables = await cursor.fetchall()

                if not tables:
                    print(f"No tables to drop, but {config.is_drop_all_tables=}")
                else:
                    table_list = ", ".join(f'"{t[0]}"' for t in tables)
                    await cursor.execute(f"DROP TABLE IF EXISTS {table_list} CASCADE;")

            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS checks(
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
            """)
    
    async def get_sum_to_pay_and_count(
        self,
        chat_id: int,
        username: str,
        total_people: int,
        geom_seq_a: float,
        geom_seq_r: float,
    ) -> tuple[int, int]:
        async with self.pg_conn.cursor() as cursor:
            await cursor.execute(
                """
                WITH existing AS (
                    SELECT count, sum_to_pay
                    FROM checks
                    WHERE chat_id = %s
                ),
                total AS (
                    SELECT COUNT(*) AS cnt
                    FROM checks
                ),
                ins AS (
                INSERT INTO checks (chat_id, username, count, total_people, sum_to_pay)
                SELECT
                    %s,  -- chat_id
                    %s,  -- username
                    total.cnt,
                    %s,  -- total_people
                    CEIL(
                        %s * POWER(%s, total.cnt)
                    )
                FROM total
                WHERE NOT EXISTS (SELECT 1 FROM existing)
                RETURNING count, sum_to_pay
                )
                SELECT
                count,
                sum_to_pay
                FROM existing

                UNION ALL

                SELECT
                count,
                sum_to_pay
                FROM ins

                LIMIT 1;
                """,
                (
                    chat_id,
                    chat_id,
                    username,
                    total_people,
                    geom_seq_a,
                    geom_seq_r,
                ),
            )
            row = await cursor.fetchone()
        
        # row[0] = count (int)
        # row[1] = sum_to_pay (int)
        return row[1], row[0]


    async def insert_check_link(self, chat_id: int, check_link: str, check_file_id: str):
        async with self.pg_conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE checks
                SET 
                    check_link       = %s,
                    check_file_id    = %s,
                    check_received_at = NOW()
                WHERE chat_id       = %s
                RETURNING 
                    count, 
                    sum_to_pay, 
                    (NOW() - first_seen_at) AS elapsed_interval;
                """,
                (check_link, check_file_id, chat_id),
            )

            result = await cursor.fetchone()
            if result is None:
                # No row with that chat_id existed
                return None, None, None

            count, sum_to_pay, elapsed_interval = result
            return count, sum_to_pay, elapsed_interval

    
    async def __del__(self):
        if self.pg_conn is not None:
            await self.pg_conn.close()
            print("pg_conn is closed")