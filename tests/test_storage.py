from concurrent.futures import ThreadPoolExecutor
from aurora import storage

def test_atomic_reservation(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB", tmp_path / "aurora.sqlite3")
    storage.reset()
    def attempt(_):
        return storage.reserve("101","salao-de-festas","2030-05-11")["ok"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,range(2)))
    assert sorted(results)==[False,True]

def test_confirmation_one_time(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,"DB",tmp_path/"aurora.sqlite3")
    storage.reset()
    sid=storage.create_session("101")
    identifier=storage.request_confirmation(sid,"reserve",{"area":"salao-de-festas","data":"2030-04-20"})
    assert storage.reservations("101")==[{"codigo":"RSV-1377","area":"quadra","data":"2030-03-09"}]
    assert storage.resolve(sid,identifier,True)["ok"]
    assert storage.resolve(sid,identifier,True) is None
    assert len(storage.reservations("101"))==2

def test_apartment_isolation(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,"DB",tmp_path/"aurora.sqlite3")
    storage.reset()
    assert not storage.cancel("101","salao-de-festas","2030-03-16")
    assert storage.reservations("302")[0]["codigo"]=="RSV-4821"
