"""测试用假 DB 层：monkeypatch app.core.db 的 fetch_one/fetch_all/execute。"""

from typing import Any, Optional


class FakeDB:
    def __init__(self):
        self.fetch_one_queue: list[Optional[dict]] = []
        self.fetch_all_queue: list[list[dict]] = []
        self.execute_queue: list[tuple[int, int]] = []
        self.executed: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, Optional[tuple]]] = []
        self.fetch_all_calls: list[tuple[str, Optional[tuple]]] = []

    def install(self, monkeypatch):
        import app.core.db as db

        async def fake_fetch_one(sql: str, args: Optional[tuple] = None):
            self.fetch_one_calls.append((sql, args))
            return self.fetch_one_queue.pop(0) if self.fetch_one_queue else None

        async def fake_fetch_all(sql: str, args: Optional[tuple] = None):
            self.fetch_all_calls.append((sql, args))
            return self.fetch_all_queue.pop(0) if self.fetch_all_queue else []

        async def fake_execute(sql: str, args: Optional[tuple] = None):
            self.executed.append((sql, args))
            return self.execute_queue.pop(0) if self.execute_queue else (0, 0)

        monkeypatch.setattr(db, "fetch_one", fake_fetch_one)
        monkeypatch.setattr(db, "fetch_all", fake_fetch_all)
        monkeypatch.setattr(db, "execute", fake_execute)
        return self


USER_ROW: dict[str, Any] = {
    "id": 7,
    "openid": "openid_test",
    "nickname": "学习者",
    "avatar_url": "",
    "total_coins": 30,
}
