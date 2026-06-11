"""Reporte oficial a Telegram via MTProto (Telethon) antes del ban.

La Bot API no expone reportSpam. Telethon corriendo con la cuenta admin
(la cuenta Telethon en este setup) sí puede:
  - messages.Report (reporte de mensaje concreto en chat)
  - account.ReportPeer (reporte de usuario en general)

Diseño: una cola asyncio. El bot encola tareas (chat_id, user_id, message_id?,
reason), y un worker en background las procesa con Telethon. Si Telethon no
está disponible (sin session, sin credenciales), las tareas se loggean y se
descartan — el ban federado se ejecuta igual.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SESSION_PATH = "/app/data/telethon.session"

# Defaults para rate limits. Configurables via .env (REPORTER_RATE_PER_HOUR/DAY).
# Telegram penaliza reportes excesivos o de baja calidad reduciendo el peso
# de la cuenta en su Native Antispam.
DEFAULT_RATE_LIMIT_PER_HOUR = 20
DEFAULT_RATE_LIMIT_PER_DAY = 100


@dataclass
class ReportTask:
    chat_id: int
    user_id: int
    message_id: Optional[int]
    reason: str  # "spam" | "fake"
    detail: str


class SpamReporter:
    """Worker async que reporta a Telegram via Telethon. Se inicia con start()."""

    def __init__(
        self, enabled: bool,
        rate_per_hour: int = DEFAULT_RATE_LIMIT_PER_HOUR,
        rate_per_day: int = DEFAULT_RATE_LIMIT_PER_DAY,
    ) -> None:
        self.enabled = enabled
        self.rate_per_hour = rate_per_hour
        self.rate_per_day = rate_per_day
        self._queue: asyncio.Queue[ReportTask] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._client = None  # type: ignore[assignment]
        self._sent_timestamps: deque[float] = deque(maxlen=rate_per_day * 2)

    def _within_rate_limit(self) -> tuple[bool, str]:
        now = time.time()
        while self._sent_timestamps and self._sent_timestamps[0] < now - 86400:
            self._sent_timestamps.popleft()
        per_hour = sum(1 for t in self._sent_timestamps if t > now - 3600)
        per_day = len(self._sent_timestamps)
        if per_hour >= self.rate_per_hour:
            return False, f"rate limit hora ({per_hour}/{self.rate_per_hour})"
        if per_day >= self.rate_per_day:
            return False, f"rate limit día ({per_day}/{self.rate_per_day})"
        return True, ""

    def is_ready(self) -> bool:
        return self.enabled and self._client is not None

    def get_client(self):
        """Devuelve el cliente Telethon o None si no está listo. Uso seguro desde otros módulos."""
        if not self.is_ready():
            return None
        return self._client

    async def start(self) -> None:
        if not self.enabled:
            log.info("SpamReporter desactivado por configuración.")
            return
        if not Path(SESSION_PATH).exists():
            log.warning(
                "SpamReporter: %s no existe. Los reportes se loggearán y se descartarán. "
                "Ejecuta scripts/telethon_login.py request/confirm para crear la sesión.",
                SESSION_PATH,
            )
            return
        api_id = os.getenv("TG_API_ID")
        api_hash = os.getenv("TG_API_HASH")
        if not api_id or not api_hash:
            log.warning("SpamReporter: faltan TG_API_ID/TG_API_HASH. Desactivado.")
            return
        try:
            from telethon import TelegramClient  # import perezoso
        except ImportError:
            log.warning("SpamReporter: telethon no instalado. Desactivado.")
            return
        try:
            self._client = TelegramClient(SESSION_PATH, int(api_id), api_hash)
            await self._client.connect()
            if not await self._client.is_user_authorized():
                log.warning("SpamReporter: sesión Telethon no autenticada. Desactivado.")
                self._client = None
                return
            me = await self._client.get_me()
            log.info(
                "SpamReporter activo como %s (@%s) id=%s",
                me.first_name, me.username, me.id,
            )
        except Exception as exc:
            log.warning("SpamReporter: fallo conectando Telethon: %s", exc)
            self._client = None
            return
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass

    def enqueue(
        self,
        chat_id: int,
        user_id: int,
        message_id: Optional[int],
        reason: str,
        detail: str,
    ) -> None:
        """Encola una tarea. No bloquea aunque el worker esté ocupado."""
        if not self.enabled:
            return
        self._queue.put_nowait(ReportTask(
            chat_id=chat_id, user_id=user_id, message_id=message_id,
            reason=reason, detail=detail,
        ))

    async def _worker(self) -> None:
        """Procesa la cola.

        Estrategia (en este orden, fallback al siguiente si falla):
          1. channels.reportSpam — mejor cuando somos admin del supergrupo y hay msg_id
          2. messages.report — reporte general con razón estandarizada
          3. account.reportPeer — reporte del usuario sin mensaje específico
        """
        from telethon.errors import RPCError
        from telethon.tl.functions.account import ReportPeerRequest
        from telethon.tl.functions.channels import ReportSpamRequest
        from telethon.tl.functions.messages import ReportRequest
        from telethon.tl.types import (
            InputReportReasonFake,
            InputReportReasonSpam,
        )

        while True:
            task: ReportTask = await self._queue.get()
            ok_rate, rate_reason = self._within_rate_limit()
            if not ok_rate:
                log.warning(
                    "SpamReporter rate-limit alcanzado (%s) — descarto reporte user=%s",
                    rate_reason, task.user_id,
                )
                continue
            try:
                reason_obj = InputReportReasonFake() if task.reason == "fake" else InputReportReasonSpam()
                detail = task.detail[:200]
                done = False

                # 1) channels.reportSpam (preferido cuando es admin y hay mensaje)
                if task.message_id and task.chat_id:
                    try:
                        chat_entity = await self._client.get_entity(task.chat_id)
                        user_entity = await self._client.get_entity(task.user_id)
                        await self._client(ReportSpamRequest(
                            channel=chat_entity,
                            participant=user_entity,
                            id=[task.message_id],
                        ))
                        log.info(
                            "channels.reportSpam OK: chat=%s msg=%s user=%s",
                            task.chat_id, task.message_id, task.user_id,
                        )
                        done = True
                    except RPCError as exc:
                        log.debug("channels.reportSpam fallo (%s), intento messages.Report", exc)
                    except Exception as exc:
                        log.debug("channels.reportSpam exc (%s), intento messages.Report", exc)

                # 2) messages.Report (mensaje específico)
                if not done and task.message_id and task.chat_id:
                    try:
                        chat_entity = await self._client.get_entity(task.chat_id)
                        await self._client(ReportRequest(
                            peer=chat_entity,
                            id=[task.message_id],
                            option=b"",
                            message=detail,
                        ))
                        log.info(
                            "messages.Report OK: chat=%s msg=%s user=%s",
                            task.chat_id, task.message_id, task.user_id,
                        )
                        done = True
                    except RPCError as exc:
                        log.debug("messages.Report fallo (%s), intento ReportPeer", exc)
                    except Exception as exc:
                        log.debug("messages.Report exc (%s), intento ReportPeer", exc)

                # 3) account.ReportPeer (usuario sin mensaje)
                if not done:
                    done = await self._report_peer(task, reason_obj, detail)
                if done:
                    self._sent_timestamps.append(time.time())
            except Exception as exc:
                log.warning("Worker reporte exc: %s", exc)
            finally:
                self._queue.task_done()

    async def _report_peer(self, task: ReportTask, reason_obj, detail: str) -> bool:
        from telethon.errors import RPCError
        from telethon.tl.functions.account import ReportPeerRequest
        try:
            user_entity = await self._client.get_entity(task.user_id)
            await self._client(ReportPeerRequest(
                peer=user_entity, reason=reason_obj, message=detail,
            ))
            log.info(
                "ReportPeer enviado: user=%s reason=%s",
                task.user_id, task.reason,
            )
            return True
        except RPCError as exc:
            log.warning("ReportPeer RPC fallo user=%s: %s", task.user_id, exc)
            return False
        except Exception as exc:
            log.warning("ReportPeer fallo user=%s: %s", task.user_id, exc)
