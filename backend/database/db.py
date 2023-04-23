import time
import aiosqlite as sqlite3

db_filename = "GQFYN.db"


async def is_username_reserved(username):
    return username == "Accounts"


async def user_exists(username):
    if await is_username_reserved(username):
        return True

    conn = await sqlite3.connect(db_filename)
    c = await conn.cursor()
    await c.execute("SELECT Username FROM Accounts WHERE Username = ?", (username,))
    if await c.fetchone() is None:
        await c.close()
        await conn.close()
        return False
    await c.close()
    await conn.close()
    return True


async def add_user(username, email, full_name, password):
    if not await user_exists(username):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(
            "INSERT INTO Accounts VALUES (?, ?, ?, ?, ?)",
            (username, email, full_name, 0, password),
        )
        await c.execute(
            f"""CREATE TABLE "{username}" (
	"NoteName"	TEXT NOT NULL UNIQUE,
	"DateModified"	INTEGER NOT NULL,
	"NoteText"	TEXT NOT NULL
)"""
        )
        await conn.commit()
        await c.close()
        await conn.close()


async def set_disabled(username, disabled):
    if await user_exists(username) and not await is_username_reserved(username):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(
            "UPDATE Accounts SET Disabled = ? WHERE Username = ?", (disabled, username)
        )
        await conn.commit()
        await c.close()
        await conn.close()


async def is_disabled(username):
    if await user_exists(username) and not await is_username_reserved(username):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute("SELECT Disabled FROM Accounts WHERE Username = ?", (username,))
        disabled = await c.fetchone()
        await c.close()
        await conn.close()
        return disabled[0] == 1
    return True


async def remove_user(username):
    if await user_exists(username) and not await is_username_reserved(username):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute("DELETE FROM Accounts WHERE Username = ?", (username,))
        await c.execute(f"DROP TABLE {username}")
        await conn.commit()
        await c.close()
        await conn.close()


async def note_exists(username, note_name):
    if await user_exists(username) and not await is_username_reserved(username):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(
            f"SELECT NoteName FROM {username} WHERE NoteName = ?", (note_name,)
        )
        if await c.fetchone() is None:
            await c.close()
            await conn.close()
            return False
        else:
            await c.close()
            await conn.close()
            return True
    return True


async def create_note(username, note_name, note_text):
    if not await note_exists(username, note_name):
        date_modified = int(time.time())

        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(
            f"INSERT INTO {username} VALUES (?, ?, ?)",
            (note_name, date_modified, note_text),
        )
        await conn.commit()
        await c.close()
        await conn.close()


async def update_note(username, note_name, note_text):
    if await note_exists(username, note_name) and not await is_username_reserved(
        username
    ):
        date_modified = int(time.time())

        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(
            f"UPDATE {username} SET DateModified = ?, NoteText = ? WHERE NoteName = ?",
            (date_modified, note_text, note_name),
        )
        await conn.commit()
        await c.close()
        await conn.close()


async def rename_note(username, note_name, new_note_name):
    if await note_exists(username, note_name) and not await note_exists(
        username, new_note_name
    ):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(
            f"UPDATE {username} SET NoteName = ? WHERE NoteName = ?",
            (new_note_name, note_name),
        )
        await conn.commit()
        await c.close()
        await conn.close()


async def delete_note(username, note_name):
    if await note_exists(username, note_name) and not await is_username_reserved(
        username
    ):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(f"DELETE FROM {username} WHERE NoteName = ?", (note_name,))
        await conn.commit()
        await c.close()
        await conn.close()


async def get_notes(username):
    if await user_exists(username) and not await is_username_reserved(username):
        conn = await sqlite3.connect(db_filename)
        c = await conn.cursor()
        await c.execute(f"SELECT NoteName, NoteText FROM {username}")
        notes = await c.fetchall()
        await c.close()
        await conn.close()
        return dict(notes)
    return {}


if __name__ == "__main__":
    import unittest

    class UnitTests(unittest.IsolatedAsyncioTestCase):
        async def test_users(self):
            self.assertFalse(await user_exists("testuser"))
            await add_user("testuser", "testemail", "testfullname", "testpassword")
            self.assertTrue(await user_exists("testuser"))
            self.assertFalse(await is_disabled("testuser"))
            await set_disabled("testuser", True)
            self.assertTrue(await is_disabled("testuser"))
            await remove_user("testuser")
            self.assertFalse(await user_exists("testuser"))

        async def test_notes(self):
            await add_user("testuser", "testemail", "testfullname", "testpassword")
            self.assertFalse(await note_exists("testuser", "testnote"))
            await create_note("testuser", "testnote", "testnotetext")
            await create_note("testuser", "testnote1", "testnotetext1")
            self.assertTrue(await note_exists("testuser", "testnote"))
            await update_note("testuser", "testnote", "testnotetext2")
            await rename_note("testuser", "testnote", "testnote2")
            self.assertFalse(await note_exists("testuser", "testnote"))
            self.assertTrue(await note_exists("testuser", "testnote2"))
            print(await get_notes("testuser"))
            await delete_note("testuser", "testnote2")
            self.assertFalse(await note_exists("testuser", "testnote2"))
            await remove_user("testuser")

            print("\n")

    unittest.main()
