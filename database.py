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
                    user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    username VARCHAR(100) NOT NULL,
                    check_link VARCHAR(300) NOT NULL,
                    check_file_id VARCHAR(300) NOT NULL
                );
            """)
    
    async def insert_check_link(self, user_id: str, chat_id: str, username: str, check_link: str, check_file_id: str):
        async with self.pg_conn.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO checks (user_id, chat_id, username, check_link, check_file_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, chat_id, username, check_link, check_file_id))
    
    async def __del__(self):
        if self.pg_conn is not None:
            await self.pg_conn.close()
            print("pg_conn is closed")