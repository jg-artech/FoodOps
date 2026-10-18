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
from typing import Optional

from agente_impresion import escpos

log = logging.getLogger("agente_impresion")


class ConfigError(Exception):
    pass


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


def bytes_para_trabajo(trabajo: dict, config: Config) -> bytes:
    tipo = trabajo.get("tipo")
    if tipo == "ticket":
        return escpos.ticket(trabajo.get("payload"), config.ancho_columnas, config.nombre_negocio)
    if tipo == "abrir_cajon":
        return escpos.abrir_cajon()
    raise ValueError(f"Tipo de trabajo desconocido: {tipo!r}")


class Agente:
    def __init__(self, config: Config, api, impresora):
        self.config, self.api, self.impresora = config, api, impresora
        # Resultados ya impresos que no se pudieron reportar (red caída). Si
        # el backend vuelve a entregar ese trabajo (timeout de 30s), se
        # reporta sin volver a imprimir: no duplica tickets ni abre el
        # cajón dos veces.
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
    log.info("Agente iniciado: backend %s, impresora %s:%s, poll cada %ss",
             config.api_url, config.impresora_ip, config.impresora_puerto, config.poll_segundos)
    impresora = ImpresoraTCP(config.impresora_ip, config.impresora_puerto, config.timeout_socket)
    try:
        Agente(config, ApiCliente(config), impresora).correr()
    except KeyboardInterrupt:
        log.info("Agente detenido")
    return 0
