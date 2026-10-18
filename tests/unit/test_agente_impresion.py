"""Agente de impresión (tools/agente_impresion) con impresora MOCK.

Ninguna prueba habla con una impresora real: se usa un transporte en
memoria y, para el código de socket, un servidor TCP local en 127.0.0.1
que solo recibe bytes.
"""
import json
import socket
import sys
import tempfile
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
    RegistroImpresos,
    TokenRechazado,
    bytes_para_trabajo,
    ruta_impresos_por_defecto,
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
    # Cada config con su propio registro temporal: las pruebas nunca
    # escriben en la ruta por defecto del usuario.
    base = dict(api_url="http://backend", token="secreto", impresora_ip="10.0.0.9",
                archivo_impresos=str(Path(tempfile.mkdtemp()) / "impresos.json"))
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


def test_config_archivo_impresos_por_entorno():
    c = Config.desde_entorno({
        "FOODOPS_API_URL": "x", "FOODOPS_AGENTE_TOKEN": "t", "FOODOPS_IMPRESORA_IP": "i",
        "FOODOPS_ARCHIVO_IMPRESOS": "/var/lib/agente/impresos.json",
    })
    assert c.archivo_impresos == "/var/lib/agente/impresos.json"


def test_ruta_por_defecto_fuera_del_repo(monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert repo not in Path(ruta_impresos_por_defecto()).parents
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\caja\AppData\Local")
    assert ruta_impresos_por_defecto().endswith("impresos.json")
    assert "FoodOpsAgente" in ruta_impresos_por_defecto()


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


# ---------------------------------------------------------------------------
# Idempotencia ante reinicio (registro local de impresos)
# ---------------------------------------------------------------------------


def test_trabajo_impreso_agente_reiniciado_no_reimprime(tmp_path):
    """Imprime, se cae antes de reportar, reinicia (proceso nuevo, misma
    ruta de registro), el backend le reentrega el trabajo: no se imprime de
    nuevo y se reporta ok."""
    archivo = tmp_path / "impresos.json"
    cfg = _config(archivo_impresos=str(archivo))
    trabajo = {"id": 42, "tipo": "abrir_cajon", "payload": {}}

    imp1 = ImpresoraMock()
    api1 = ApiMock([trabajo], falla_reporte=1)   # se cae antes de reportar
    Agente(cfg, api1, imp1).ciclo()
    assert len(imp1.enviados) == 1 and api1.reportes == []
    assert json.loads(archivo.read_text())["impresos"] == [42]

    # Reinicio: instancia nueva, nada en memoria.
    imp2 = ImpresoraMock()
    api2 = ApiMock([trabajo])                    # reentrega tras el timeout de 30s
    Agente(cfg, api2, imp2).ciclo()
    assert imp2.enviados == []
    assert api2.reportes == [(42, "ok", None)]


def test_trabajo_con_error_si_se_reintenta_tras_reinicio(tmp_path):
    """Solo se registra lo impreso con éxito: un trabajo que falló y se
    reintenta desde el sistema se vuelve a intentar imprimir."""
    cfg = _config(archivo_impresos=str(tmp_path / "impresos.json"))
    trabajo = {"id": 43, "tipo": "abrir_cajon", "payload": {}}
    Agente(cfg, ApiMock([trabajo]), ImpresoraMock(falla_en={"todo"})).ciclo()

    imp = ImpresoraMock()
    api = ApiMock([trabajo])
    Agente(cfg, api, imp).ciclo()
    assert len(imp.enviados) == 1 and api.reportes == [(43, "ok", None)]


def test_registro_corrupto_arranca_vacio(tmp_path):
    archivo = tmp_path / "impresos.json"
    archivo.write_text("{no es json")
    r = RegistroImpresos(str(archivo))
    assert not r.contiene(1)
    r.agregar(1)
    assert RegistroImpresos(str(archivo)).contiene(1)


def test_registro_se_acota(tmp_path, monkeypatch):
    monkeypatch.setattr(RegistroImpresos, "MAXIMO", 3)
    r = RegistroImpresos(str(tmp_path / "impresos.json"))
    for i in range(5):
        r.agregar(i)
    r2 = RegistroImpresos(str(tmp_path / "impresos.json"))
    assert [r2.contiene(i) for i in range(5)] == [False, False, True, True, True]


# ---------------------------------------------------------------------------
# Log del agente sin consola (pythonw.exe en la tarea programada)
# ---------------------------------------------------------------------------


@pytest.fixture
def logging_aislado():
    """Restaura handlers del logger raíz y sys.excepthook tras la prueba."""
    import logging

    raiz = logging.getLogger()
    handlers, nivel, hook = list(raiz.handlers), raiz.level, sys.excepthook
    yield
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
        h.close()
    for h in handlers:
        raiz.addHandler(h)
    raiz.setLevel(nivel)
    sys.excepthook = hook


def _leer(ruta):
    import logging

    for h in logging.getLogger().handlers:
        h.flush()
    return Path(ruta).read_text(encoding="utf-8")


def test_sin_consola_escribe_en_log_por_defecto(tmp_path, monkeypatch, logging_aislado):
    from agente_impresion.agente import configurar_log, log

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "stderr", None)  # como pythonw.exe
    archivo = configurar_log({})
    assert archivo == str(tmp_path / "FoodOpsAgente" / "agente.log")
    log.info("Agente iniciado: prueba ñandú")
    assert "Agente iniciado: prueba ñandú" in _leer(archivo)


def test_archivo_log_por_variable_de_entorno(tmp_path, logging_aislado):
    from agente_impresion.agente import configurar_log, log

    destino = tmp_path / "otra" / "carpeta" / "agente.log"
    assert configurar_log({"FOODOPS_ARCHIVO_LOG": str(destino)}) == str(destino)
    log.warning("aviso de prueba")
    assert "WARNING aviso de prueba" in _leer(destino)


def test_con_consola_y_sin_variable_no_crea_archivo(tmp_path, monkeypatch, logging_aislado):
    import logging

    from agente_impresion.agente import configurar_log

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert configurar_log({}) is None
    assert not (tmp_path / "FoodOpsAgente").exists()
    assert all(not isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers)


def test_error_no_controlado_queda_en_el_log(tmp_path, logging_aislado):
    from agente_impresion.agente import configurar_log

    destino = tmp_path / "agente.log"
    configurar_log({"FOODOPS_ARCHIVO_LOG": str(destino)})
    try:
        raise RuntimeError("fallo simulado")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    contenido = _leer(destino)
    assert "Error no controlado" in contenido and "RuntimeError: fallo simulado" in contenido


def test_log_es_rotativo(tmp_path, logging_aislado):
    import logging

    from agente_impresion.agente import LOG_MAX_BYTES, LOG_RESPALDOS, configurar_log

    configurar_log({"FOODOPS_ARCHIVO_LOG": str(tmp_path / "agente.log")})
    (h,) = logging.getLogger().handlers
    assert isinstance(h, logging.handlers.RotatingFileHandler)
    assert h.maxBytes == LOG_MAX_BYTES and h.backupCount == LOG_RESPALDOS


# ---------------------------------------------------------------------------
# El token nunca llega al log
# ---------------------------------------------------------------------------

TOKEN_PRUEBA = "TOKEN-DE-PRUEBA-a1b2c3d4e5"


@pytest.fixture
def secretos_aislados():
    from agente_impresion import agente

    antes = set(agente._SECRETOS)
    yield
    agente._SECRETOS.clear()
    agente._SECRETOS.update(antes)


def test_error_no_controlado_no_escribe_el_token(tmp_path, logging_aislado, secretos_aislados):
    """Error no controlado cuyo mensaje incluye el token: el log lo oculta, y
    el traceback no vuelca variables locales."""
    from agente_impresion.agente import configurar_log, registrar_secreto

    destino = tmp_path / "agente.log"
    configurar_log({"FOODOPS_ARCHIVO_LOG": str(destino)})
    registrar_secreto(TOKEN_PRUEBA)

    def falla():
        config_local = "VALOR-LOCAL-NO-DEBE-SALIR"  # noqa: F841 - prueba de locals
        raise RuntimeError(f"fallo con Bearer {TOKEN_PRUEBA}")

    try:
        falla()
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    contenido = _leer(destino)
    assert "Error no controlado" in contenido and "RuntimeError" in contenido
    assert TOKEN_PRUEBA not in contenido
    assert "Bearer ***" in contenido
    assert "VALOR-LOCAL-NO-DEBE-SALIR" not in contenido


def test_header_invalido_no_filtra_el_token(tmp_path, logging_aislado, secretos_aislados):
    """Camino real encontrado: un token con salto de línea hace que
    http.client lance 'Invalid header value b"Bearer <token>\\n"', que el
    agente registra como 'Sin conexión'. El log debe mostrar ***."""
    from agente_impresion.agente import ApiCliente, configurar_log, registrar_secreto

    destino = tmp_path / "agente.log"
    configurar_log({"FOODOPS_ARCHIVO_LOG": str(destino)})
    token_sucio = TOKEN_PRUEBA + "\n"
    registrar_secreto(token_sucio)
    cfg = _config(api_url="http://127.0.0.1:9", token=token_sucio)

    def dormir(_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Agente(cfg, ApiCliente(cfg), ImpresoraMock()).correr(dormir=dormir)
    contenido = _leer(destino)
    assert "Sin conexión con el backend" in contenido
    assert TOKEN_PRUEBA not in contenido


def test_token_se_limpia_y_se_valida_sin_mostrarlo():
    base = {"FOODOPS_API_URL": "http://x", "FOODOPS_IMPRESORA_IP": "i"}
    c = Config.desde_entorno({**base, "FOODOPS_AGENTE_TOKEN": f"  {TOKEN_PRUEBA}\r\n"})
    assert c.token == TOKEN_PRUEBA
    for malo in (f"{TOKEN_PRUEBA} extra", f"{TOKEN_PRUEBA}\x00", "token/con/barras"):
        with pytest.raises(ConfigError) as e:
            Config.desde_entorno({**base, "FOODOPS_AGENTE_TOKEN": malo})
        assert TOKEN_PRUEBA not in str(e.value) and "barras" not in str(e.value)


def test_proceso_real_con_token_invalido_no_lo_escribe(tmp_path):
    """python -m agente_impresion de verdad, con log a archivo: token con un
    espacio en medio -> sale con 2 y el log no contiene el token."""
    import os
    import subprocess

    destino = tmp_path / "agente.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith("FOODOPS_")}
    env.update({
        "FOODOPS_API_URL": "http://127.0.0.1:9",
        "FOODOPS_AGENTE_TOKEN": f"{TOKEN_PRUEBA} copiado-mal",
        "FOODOPS_IMPRESORA_IP": "127.0.0.1",
        "FOODOPS_ARCHIVO_LOG": str(destino),
        "LOCALAPPDATA": str(tmp_path),
    })
    r = subprocess.run([sys.executable, "-m", "agente_impresion"],
                       cwd=Path(__file__).resolve().parents[2] / "tools",
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 2
    contenido = destino.read_text(encoding="utf-8")
    assert "FOODOPS_AGENTE_TOKEN tiene espacios o caracteres no válidos" in contenido
    assert TOKEN_PRUEBA not in contenido + r.stdout + r.stderr
