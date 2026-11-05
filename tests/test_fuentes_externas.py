import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import db
from data import sources


class Response:
    status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return {"results": [{
            "id": 123, "observed_on": "2026-05-01", "location": "-16.5,-68.1",
            "place_guess": "La Paz", "description": "Observación de prueba",
            "uri": "https://www.inaturalist.org/observations/123",
            "taxon": {"name": "Testus avis", "iconic_taxon_name": "Aves"},
            "photos": [{"id": 7, "url": "https://example.org/small.jpg", "license_code": "cc-by"}],
            "sounds": [{"id": 8, "file_url": "https://example.org/test.mp3", "license_code": "cc-by"}],
            "positional_accuracy": 20
        }]}


def test_inat_importa_evento_con_modalidades_independientes(tmp_path):
    from config import Config
    cfg = Config(store=str(tmp_path / "store"), db=str(tmp_path / "store" / "test.db"))
    con = db.init(cfg)
    calls = []
    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return Response()
    n = sources.recolectar_inaturalist(con, objetivo=2, taxa={"Aves": 3},
                                       paginas_max=1, pausa=0, get=fake_get)
    assert n == 2
    assert con.execute("select count(*) from events").fetchone()[0] == 1
    assert con.execute("select count(*) from images").fetchone()[0] == 1
    assert con.execute("select count(*) from audio").fetchone()[0] == 1
    assert con.execute("select link_type from events").fetchone()[0] == "event"
    con.close()


def test_xenocanto_importa_audio_y_enlace_por_especie(tmp_path):
    from config import Config
    cfg = Config(store=str(tmp_path / "store"), db=str(tmp_path / "store" / "test.db"))
    con = db.init(cfg)
    def fake_get(url, params=None, headers=None, timeout=None):
        class R(Response):
            def json(self):
                return {"recordings": [{
                    "id": "999", "gen": "Testus", "sp": "avis", "lat": "-16.5",
                    "lng": "-68.1", "loc": "La Paz", "date": "2025-01-01",
                    "file": "https://example.org/audio.mp3", "lic": "CC-BY",
                    "rec": "Recorder", "rmk": "Canto"
                }]}
        return R()
    out = sources.recolectar_xenocanto(con, objetivo=1, api_key="dummy", get=fake_get)
    assert out["agregados"] == 1
    assert con.execute("select link_type from events").fetchone()[0] == "species"
    assert con.execute("select count(*) from audio").fetchone()[0] == 1
    assert con.execute("select count(*) from geo").fetchone()[0] == 1
    con.close()


def test_gbif_acepta_registro_con_solo_fotografia_y_sin_filtrar_licencia(tmp_path):
    from config import Config
    from data import collect
    cfg = Config(store=str(tmp_path / "store"), db=str(tmp_path / "store" / "test.db"))
    con = db.init(cfg)
    registro = {
        "key": 555, "species": "Testus imago", "scientificName": "Testus imago",
        "eventDate": "2026-01-01", "decimalLatitude": -16.5, "decimalLongitude": -68.1,
        "class": "Aves", "license": "ARR",
        "media": [{"type": "StillImage", "identifier": "https://example.org/photo.jpg",
                   "license": "ARR", "creator": "Test"}]
    }
    assert collect.guardar(con, registro, por_especie=10) is True
    assert con.execute("select count(*) from images").fetchone()[0] == 1
    assert con.execute("select count(*) from audio").fetchone()[0] == 0
    assert con.execute("select license from images").fetchone()[0] == "ARR"
    con.close()
