"""Agente de impresión (tools/agente_impresion) con impresora MOCK.

Ninguna prueba habla con una impresora real: se usa un transporte en
memoria y, para el código de socket, un servidor TCP local en 127.0.0.1
que solo recibe bytes.
"""
import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from agente_impresion import escpos  # noqa: E402
from agente_impresion.agente import (  # noqa: E402
    Agente,
    Config,
    ConfigError,
    ImpresoraTCP,
    TokenRechazado,
    bytes_para_trabajo,
)

PULSO = bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])

ORDEN = {
    "id": 7,
    "numero_orden": "ORD-1-20261018120000",
    "total": 85.0,
    "metodo_pago": "efectivo",
    "dinero_recibido": 100.0,
    "vuelto": 15.0,
    "monto_recibido": 200.0,
    "vuelto_entregado": 115.0,
    "es_domicilio": True,
    "cliente_nombre": "Juan\x1bp\x00\x19\xfaPérez",  # intento de inyectar ESC/POS
    "cliente_telefono": "5555-1234",
    "cliente_direccion": "Zona 1",
    "notas_especiales": "Sin cebolla",
    "punto_nombre": "Centro",
    "tomada_por_nombre": "Ana",
    "created_at": "2026-10-18 18:30:00.123456",
    "items": [
        {"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 85.0,
         "subtotal": 85.0, "especiales": "pierna"},
    ],
}


def _config(**kw):
    base = dict(api_url="http://backend", token="secreto", impresora_ip="10.0.0.9")
    base.update(kw)
    return Config(**base)


class ImpresoraMock:
    def __init__(self, falla_en=()):
        self.enviados: list[bytes] = []
        self.falla_en = set(falla_en)

    def enviar(self, datos: bytes) -> None:
        if datos in self.falla_en or (PULSO in datos and "cajon" in self.falla_en):
            raise OSError("impresora sin papel")
        if "todo" in self.falla_en:
            raise ConnectionRefusedError("impresora apagada")
        self.enviados.append(datos)


class ApiMock:
    def __init__(self, trabajos=None, falla_reporte=0):
        self.trabajos = list(trabajos or [])
        self.reportes: list[tuple] = []
        self.falla_reporte = falla_reporte

    def pendientes(self):
        t, self.trabajos = self.trabajos, []
        return t

    def reportar(self, trabajo_id, estado, error=None):
        if self.falla_reporte:
            self.falla_reporte -= 1
            raise OSError("red caída")
        self.reportes.append((trabajo_id, estado, error))


# ---------------------------------------------------------------------------
# ESC/POS
# ---------------------------------------------------------------------------


def test_pulso_cajon_exacto():
    assert escpos.PULSO_CAJON == PULSO
    assert escpos.abrir_cajon() == b"\x1b@" + PULSO


def test_ticket_es_escpos_con_corte_y_sin_html():
    datos = escpos.ticket({"version": 1, "orden": ORDEN})
    assert datos.startswith(b"\x1b@\x1bt\x02")       # init + CP850
    assert datos.endswith(b"\x1dV\x42\x00")           # corte
    texto = datos.decode("cp850")
    for esperado in ("ORD-1-20261018120000", "1x 1/4 Pollo", "Q85.00", "TOTAL",
                     "Efectivo", "Centro", "Atendió:", "Sin cebolla", "> pierna"):
        assert esperado in texto, esperado
    assert "<" not in texto and "html" not in texto.lower()


def test_ticket_usa_montos_confirmados_por_el_responsable():
    texto = escpos.ticket({"orden": ORDEN}).decode("cp850")
    assert "Q200.00" in texto and "Q115.00" in texto


def test_ticket_no_permite_inyectar_comandos_desde_los_datos():
    datos = escpos.ticket({"orden": ORDEN})
    assert PULSO not in datos
    assert b"\x1bp" not in datos
    assert "JuanpúPérez" in datos.decode("cp850")  # sin los bytes de control


def test_ticket_respeta_el_ancho():
    datos = escpos.ticket({"orden": {**ORDEN, "notas_especiales": "x" * 200}}, ancho=32)
    for linea in datos.split(b"\n"):
        visible = bytes(b for b in linea if b >= 0x20)
        # Los comandos ESC/GS llevan argumentos imprimibles: tolerancia mínima.
        assert len(visible) <= 32 + 4


@pytest.mark.parametrize("payload", [None, "<html>ticket</html>", {"orden": "x"}, {}])
def test_ticket_rechaza_payload_que_no_es_json_de_orden(payload):
    with pytest.raises(ValueError):
        escpos.ticket(payload)


# ---------------------------------------------------------------------------
# Config por entorno
# ---------------------------------------------------------------------------


def test_config_solo_por_entorno():
    c = Config.desde_entorno({
        "FOODOPS_API_URL": "https://api.ejemplo/",
        "FOODOPS_AGENTE_TOKEN": "tok",
        "FOODOPS_IMPRESORA_IP": "192.168.1.50",
    })
    assert c.api_url == "https://api.ejemplo"
    assert c.impresora_puerto == 9100 and c.poll_segundos == 5
    assert "tok" not in repr(c)


def test_config_falta_variable():
    with pytest.raises(ConfigError) as e:
        Config.desde_entorno({"FOODOPS_API_URL": "x"})
    assert "FOODOPS_AGENTE_TOKEN" in str(e.value)


# ---------------------------------------------------------------------------
# Ciclo del agente con mocks
# ---------------------------------------------------------------------------


def test_ticket_y_cajon_se_envian_y_reportan_ok():
    api = ApiMock([
        {"id": 1, "tipo": "ticket", "payload": {"orden": ORDEN}},
        {"id": 2, "tipo": "abrir_cajon", "payload": {}},
    ])
    imp = ImpresoraMock()
    assert Agente(_config(), api, imp).ciclo() == 2
    assert imp.enviados[1] == b"\x1b@" + PULSO
    assert PULSO not in imp.enviados[0]
    assert api.reportes == [(1, "ok", None), (2, "ok", None)]


def test_impresion_falla_y_cajon_abre_cada_uno_su_estado():
    api = ApiMock([
        {"id": 1, "tipo": "ticket", "payload": {"orden": ORDEN}},
        {"id": 2, "tipo": "abrir_cajon", "payload": {}},
    ])
    ticket_bytes = bytes_para_trabajo(api.trabajos[0], _config())
    Agente(_config(), api, ImpresoraMock(falla_en={ticket_bytes})).ciclo()
    assert api.reportes[0][:2] == (1, "error") and "sin papel" in api.reportes[0][2]
    assert api.reportes[1] == (2, "ok", None)


def test_cajon_falla_e_impresion_ok():
    api = ApiMock([
        {"id": 1, "tipo": "ticket", "payload": {"orden": ORDEN}},
        {"id": 2, "tipo": "abrir_cajon", "payload": {}},
    ])
    Agente(_config(), api, ImpresoraMock(falla_en={"cajon"})).ciclo()
    assert api.reportes[0] == (1, "ok", None)
    assert api.reportes[1][:2] == (2, "error")


def test_tipo_desconocido_se_reporta_como_error_sin_imprimir():
    api = ApiMock([{"id": 5, "tipo": "comanda", "payload": {}}])
    imp = ImpresoraMock()
    Agente(_config(), api, imp).ciclo()
    assert imp.enviados == []
    assert api.reportes[0][:2] == (5, "error")


def test_si_no_pudo_reportar_no_reimprime_al_volver_a_recibirlo():
    """Red caída al reportar: el backend reentrega el trabajo tras 30s; el
    agente lo reporta sin abrir el cajón otra vez."""
    trabajo = {"id": 9, "tipo": "abrir_cajon", "payload": {}}
    api = ApiMock([trabajo], falla_reporte=1)
    imp = ImpresoraMock()
    agente = Agente(_config(), api, imp)
    agente.ciclo()
    assert len(imp.enviados) == 1 and api.reportes == []

    api.trabajos = [trabajo]   # reentrega por timeout
    api.falla_reporte = 1      # y el reintento previo al poll también falla
    agente.ciclo()
    assert len(imp.enviados) == 1            # no se volvió a abrir el cajón
    assert api.reportes == [(9, "ok", None)]


def test_token_rechazado_corta_el_ciclo():
    class ApiRechaza(ApiMock):
        def pendientes(self):
            raise TokenRechazado()

    esperas = []

    def dormir(s):
        esperas.append(s)
        raise KeyboardInterrupt  # corta el while True tras la primera vuelta

    with pytest.raises(KeyboardInterrupt):
        Agente(_config(), ApiRechaza(), ImpresoraMock()).correr(dormir=dormir)
    assert esperas == [60.0]


# ---------------------------------------------------------------------------
# Socket real contra un servidor local (impresora mock en 127.0.0.1)
# ---------------------------------------------------------------------------


def test_impresora_tcp_envia_bytes_por_socket():
    srv = socket.create_server(("127.0.0.1", 0))
    puerto = srv.getsockname()[1]
    recibido = bytearray()

    def atender():
        conn, _ = srv.accept()
        with conn:
            while chunk := conn.recv(4096):
                recibido.extend(chunk)

    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    ImpresoraTCP("127.0.0.1", puerto, timeout=2).enviar(escpos.abrir_cajon())
    hilo.join(timeout=2)
    srv.close()
    assert bytes(recibido) == b"\x1b@" + PULSO


def test_impresora_tcp_apagada_lanza_error():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()  # nadie escucha en ese puerto
    with pytest.raises(OSError):
        ImpresoraTCP("127.0.0.1", puerto, timeout=1).enviar(b"x")


# ---------------------------------------------------------------------------
# Extremo a extremo: lógica real del agente contra el backend real (TestClient)
# ---------------------------------------------------------------------------


def test_agente_contra_backend_real(api, engine):
    """El agente toma un ABRIR_CAJON del backend, lo "imprime" en el mock y
    el backend queda en ok."""
    import uuid

    from sqlalchemy.orm import sessionmaker

    from foodops.core.auth import create_access_token, hash_password
    from foodops.db.models import Empresa, PuntoVenta, TrabajoImpresion, Usuario, UserRol

    s = sessionmaker(bind=engine)()
    emp = Empresa(nombre="Agente E2E", nit=f"E2E-{uuid.uuid4().hex[:8]}")
    s.add(emp)
    s.flush()
    p = PuntoVenta(empresa_id=emp.id, nombre="E2E", impresora_activa=True, cajon_activo=True)
    s.add(p)
    s.flush()
    admin = Usuario(empresa_id=emp.id, punto_id=p.id, username=f"e2e_{uuid.uuid4().hex[:6]}",
                    email=f"e2e_{uuid.uuid4().hex[:6]}@t.gt", password_hash=hash_password("x" * 8),
                    rol=UserRol.ADMIN)
    s.add(admin)
    s.commit()
    jwt = create_access_token(data={"user_id": admin.id, "username": admin.username,
                                    "punto_id": p.id, "rol": "admin", "empresa_id": emp.id})
    auth = {"Authorization": f"Bearer {jwt}"}

    token = api.post(f"/api/puntos-venta/{p.id}/regenerar-token-agente", headers=auth).json()["token"]
    r = api.post("/api/impresion/abrir-cajon", json={"motivo": "prueba e2e"}, headers=auth)
    trabajo_id = r.json()["id"]

    class ApiTestClient:
        h = {"Authorization": f"Bearer {token}"}

        def pendientes(self):
            r = api.get("/api/impresion/agente/pendientes", headers=self.h)
            assert r.status_code == 200
            return r.json()

        def reportar(self, tid, estado, error=None):
            body = {"estado": estado, **({"error": error} if error else {})}
            assert api.post(f"/api/impresion/agente/trabajos/{tid}/resultado",
                            json=body, headers=self.h).status_code == 200

    imp = ImpresoraMock()
    Agente(_config(), ApiTestClient(), imp).ciclo()
    assert imp.enviados == [b"\x1b@" + PULSO]
    s.expire_all()
    assert s.get(TrabajoImpresion, trabajo_id).estado == "ok"
    s.close()
