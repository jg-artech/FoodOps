"""Agente de impresión de tienda: polling al backend + ESC/POS por socket.

Ver README.md y docs/DISENO_IMPRESION.md §6-§9. Solo biblioteca estándar,
para que empaquetarlo en Windows (pyinstaller) sea trivial.

El token del agente nunca se escribe en el log.
"""
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agente_impresion import escpos

log = logging.getLogger("agente_impresion")


class ConfigError(Exception):
    pass


def ruta_impresos_por_defecto() -> str:
    """Fuera del repo y de la carpeta del ejecutable: en Windows
    %LOCALAPPDATA%\\FoodOpsAgente, en otros sistemas ~/.local/state."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return str(Path(base) / "FoodOpsAgente" / "impresos.json")
    return str(Path.home() / ".local" / "state" / "foodops-agente" / "impresos.json")


@dataclass(frozen=True)
class Config:
    api_url: str
    # repr=False: que el token no salga si alguien loguea la config.
    token: str = field(repr=False)
    impresora_ip: str
    impresora_puerto: int = 9100
    poll_segundos: float = 5.0
    timeout_socket: float = 5.0
    timeout_http: float = 10.0
    ancho_columnas: int = 42
    nombre_negocio: str = "Asados a la Leña"
    archivo_impresos: str = field(default_factory=ruta_impresos_por_defecto)

    @classmethod
    def desde_entorno(cls, env=None) -> "Config":
        """Configuración SOLO por variables de entorno."""
        env = os.environ if env is None else env
        requeridas = ("FOODOPS_API_URL", "FOODOPS_AGENTE_TOKEN", "FOODOPS_IMPRESORA_IP")
        faltan = [v for v in requeridas if not env.get(v)]
        if faltan:
            raise ConfigError("Faltan variables de entorno: " + ", ".join(faltan))
        try:
            return cls(
                api_url=env["FOODOPS_API_URL"].rstrip("/"),
                token=env["FOODOPS_AGENTE_TOKEN"],
                impresora_ip=env["FOODOPS_IMPRESORA_IP"],
                impresora_puerto=int(env.get("FOODOPS_IMPRESORA_PUERTO", 9100)),
                poll_segundos=float(env.get("FOODOPS_POLL_SEGUNDOS", 5)),
                timeout_socket=float(env.get("FOODOPS_TIMEOUT_SOCKET", 5)),
                timeout_http=float(env.get("FOODOPS_TIMEOUT_HTTP", 10)),
                ancho_columnas=int(env.get("FOODOPS_ANCHO_COLUMNAS", 42)),
                nombre_negocio=env.get("FOODOPS_NOMBRE_NEGOCIO", "Asados a la Leña"),
                archivo_impresos=(
                    env.get("FOODOPS_ARCHIVO_IMPRESOS") or ruta_impresos_por_defecto()
                ),
            )
        except ValueError as e:
            raise ConfigError(f"Variable de entorno con valor inválido: {e}") from None


class ImpresoraTCP:
    """Envía bytes crudos al puerto ESC/POS (9100) de la impresora."""

    def __init__(self, ip: str, puerto: int, timeout: float):
        self.ip, self.puerto, self.timeout = ip, puerto, timeout

    def enviar(self, datos: bytes) -> None:
        with socket.create_connection((self.ip, self.puerto), timeout=self.timeout) as s:
            s.sendall(datos)


class TokenRechazado(Exception):
    """401: token inválido o revocado. No tiene sentido reintentar rápido."""


class ApiCliente:
    def __init__(self, config: Config):
        self._base = config.api_url + "/api/impresion/agente"
        self._token = config.token
        self._timeout = config.timeout_http

    def _request(self, metodo: str, ruta: str, cuerpo: Optional[dict] = None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(self._base + ruta, data=datos, method=metodo)
        req.add_header("Authorization", f"Bearer {self._token}")
        if datos is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise TokenRechazado() from None
            raise

    def pendientes(self) -> list:
        return self._request("GET", "/pendientes")

    def reportar(self, trabajo_id: int, estado: str, error: Optional[str] = None) -> None:
        cuerpo = {"estado": estado}
        if error:
            cuerpo["error"] = error[:1000]
        try:
            self._request("POST", f"/trabajos/{trabajo_id}/resultado", cuerpo)
        except urllib.error.HTTPError as e:
            # 409: el backend ya tiene un resultado final para ese trabajo.
            if e.code != 409:
                raise


class RegistroImpresos:
    """Ids de trabajos ya impresos con éxito, persistidos en un archivo local.

    Idempotencia ante reinicios (docs/DISENO_IMPRESION.md §5, opción b): el
    backend reentrega un trabajo IMPRIMIENDO a los 30s si no recibe
    resultado. Si el agente imprimió y se reinició antes de reportar, al
    recibirlo de nuevo lo encuentra aquí y solo reporta "ok", sin volver a
    imprimir ni a abrir el cajón.

    Se escribe DESPUÉS de imprimir y ANTES de reportar. Queda una ventana
    mínima sin cubrir: si el proceso muere entre el envío a la impresora y
    esta escritura, ese trabajo se imprimirá otra vez.
    """

    MAXIMO = 5000  # los más viejos ya no pueden volver a entregarse

    def __init__(self, ruta: str):
        self.ruta = Path(ruta)
        self._ids: list[int] = []
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            self._ids = [int(i) for i in datos.get("impresos", [])]
        except FileNotFoundError:
            pass
        except (ValueError, OSError, AttributeError, TypeError) as e:
            log.warning("Registro de impresos ilegible (%s), se empieza vacío: %s", self.ruta, e)
        self._set = set(self._ids)

    def contiene(self, trabajo_id: int) -> bool:
        return trabajo_id in self._set

    def agregar(self, trabajo_id: int) -> None:
        if trabajo_id in self._set:
            return
        self._ids.append(trabajo_id)
        self._ids = self._ids[-self.MAXIMO:]
        self._set = set(self._ids)
        # Escritura atómica: archivo temporal + fsync + os.replace, para que
        # un corte de luz no deje el JSON a medias.
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"impresos": self._ids}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.ruta)


def bytes_para_trabajo(trabajo: dict, config: Config) -> bytes:
    tipo = trabajo.get("tipo")
    if tipo == "ticket":
        return escpos.ticket(trabajo.get("payload"), config.ancho_columnas, config.nombre_negocio)
    if tipo == "abrir_cajon":
        return escpos.abrir_cajon()
    raise ValueError(f"Tipo de trabajo desconocido: {tipo!r}")


class Agente:
    def __init__(self, config: Config, api, impresora, registro: Optional[RegistroImpresos] = None):
        self.config, self.api, self.impresora = config, api, impresora
        # Persistente: sobrevive a reinicios del agente (ver RegistroImpresos).
        self.registro = registro or RegistroImpresos(config.archivo_impresos)
        # Resultados que no se pudieron reportar (red caída), para
        # reintentar el reporte en el siguiente ciclo. Solo en memoria: tras
        # un reinicio, lo impreso lo cubre self.registro.
        self._sin_reportar: dict[int, tuple[str, Optional[str]]] = {}

    def _reportar(self, trabajo_id: int, estado: str, error: Optional[str]) -> None:
        try:
            self.api.reportar(trabajo_id, estado, error)
            self._sin_reportar.pop(trabajo_id, None)
        except TokenRechazado:
            self._sin_reportar[trabajo_id] = (estado, error)
            raise
        except Exception as e:
            log.warning("No se pudo reportar el trabajo %s: %s", trabajo_id, e)
            self._sin_reportar[trabajo_id] = (estado, error)

    def procesar(self, trabajo: dict) -> str:
        tid = trabajo["id"]
        if self.registro.contiene(tid):
            # Ya se imprimió (quizá antes de un reinicio): solo reportar.
            log.info("Trabajo %s ya impreso antes, se reporta sin reimprimir", tid)
            self._reportar(tid, "ok", None)
            return "ok"
        if tid in self._sin_reportar:
            estado, error = self._sin_reportar[tid]
            self._reportar(tid, estado, error)
            return estado
        try:
            self.impresora.enviar(bytes_para_trabajo(trabajo, self.config))
            estado, error = "ok", None
            log.info("Trabajo %s (%s) impreso", tid, trabajo.get("tipo"))
        except Exception as e:
            estado, error = "error", f"{type(e).__name__}: {e}"
            log.error("Trabajo %s (%s) falló: %s", tid, trabajo.get("tipo"), error)
        if estado == "ok":
            # Antes de reportar: si el agente muere ahora, al reiniciar no
            # vuelve a imprimirlo.
            try:
                self.registro.agregar(tid)
            except OSError as e:
                log.error("No se pudo guardar el trabajo %s como impreso: %s", tid, e)
        self._reportar(tid, estado, error)
        return estado

    def ciclo(self) -> int:
        """Un poll: reintenta reportes atrasados, pide pendientes y los
        procesa uno por uno. Cada trabajo reporta su propio resultado."""
        for tid, (estado, error) in list(self._sin_reportar.items()):
            self._reportar(tid, estado, error)
        trabajos = self.api.pendientes() or []
        for t in trabajos:
            self.procesar(t)
        return len(trabajos)

    def correr(self, dormir=time.sleep) -> None:
        while True:
            try:
                self.ciclo()
                espera = self.config.poll_segundos
            except TokenRechazado:
                log.error("El backend rechazó el token del agente (inválido o revocado). "
                          "Regenérelo y actualice FOODOPS_AGENTE_TOKEN.")
                espera = max(60.0, self.config.poll_segundos)
            except Exception as e:
                log.warning("Sin conexión con el backend: %s", e)
                espera = self.config.poll_segundos
            dormir(espera)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = Config.desde_entorno()
    except ConfigError as e:
        log.error("%s", e)
        return 2
    log.info("Agente iniciado: backend %s, impresora %s:%s, poll cada %ss, registro %s",
             config.api_url, config.impresora_ip, config.impresora_puerto, config.poll_segundos,
             config.archivo_impresos)
    impresora = ImpresoraTCP(config.impresora_ip, config.impresora_puerto, config.timeout_socket)
    try:
        Agente(config, ApiCliente(config), impresora).correr()
    except KeyboardInterrupt:
        log.info("Agente detenido")
    return 0
