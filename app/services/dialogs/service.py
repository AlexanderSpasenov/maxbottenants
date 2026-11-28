from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.crypto import encrypt_value, mask_phone
from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.customer_profile_repository import CustomerProfileRepository
from app.repositories.dialog_session_repository import DialogSessionRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.tenant_link_repository import TenantLinkRepository
from app.repositories.tenant_member_repository import TenantMemberRepository
from app.repositories.tenant_repository import TenantRepository
from app.services.dialogs import state_machine as sm

logger = logging.getLogger(__name__)


class DialogService:
    def __init__(self, db: Session):
        self.db = db
        self.tenants = TenantRepository(db)
        self.links = TenantLinkRepository(db)
        self.members = TenantMemberRepository(db)
        self.sessions = DialogSessionRepository(db)
        self.catalog = CatalogRepository(db)
        self.bookings = BookingRepository(db)
        self.customers = CustomerProfileRepository(db)
        self.outbox = OutboxRepository(db)

    def handle_event(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        event_type = str(payload.get("update_type") or "unknown")
        if event_type == "message_created":
            return self._handle_message(payload)
        if event_type == "message_callback":
            return self._handle_callback(payload)
        return []

    def _handle_message(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        from app.services.webhooks.normalizer import normalize_max_event

        n = normalize_max_event(payload)
        chat_id = int(n.get("chat_id") or 0)
        max_user_id = int(n.get("user_id") or 0)
        text = str(n.get("text") or "").strip()
        if not chat_id or not max_user_id:
            return []

        session = self.sessions.get(chat_id)
        if session is None:
            session = self.sessions.upsert(
                chat_id=chat_id, max_user_id=max_user_id, current_step=sm.START, context={}
            )
        # Keep max_user_id in context for response routing
        sctx = dict(session.context or {})
        if sctx.get("max_user_id") != max_user_id:
            sctx["max_user_id"] = max_user_id
            session.context = sctx
            self.db.add(session)

        if text.startswith("/start") or text.lower() in {"/menu", "меню", "start"}:
            if text.startswith("/start"):
                return self._handle_start(session, chat_id, max_user_id, text)
            tenant = self._resolve_tenant(session)
            if tenant and tenant.status == "active":
                self.sessions.upsert(
                    chat_id=chat_id,
                    max_user_id=max_user_id,
                    current_tenant_id=tenant.id,
                    current_step=sm.MENU,
                    context={"tenant_slug": tenant.slug},
                )
                self.db.commit()
                return [self._menu_message(chat_id, tenant.display_name, max_user_id)]
            return self._handle_start(session, chat_id, max_user_id, "/start")

        owner_response = self._handle_owner_command(chat_id, max_user_id, text)
        if owner_response is not None:
            self.db.commit()
            return owner_response

        return self._handle_text_step(session, chat_id, max_user_id, text)

    def _handle_start(self, session, chat_id: int, max_user_id: int, text: str):
        parts = text.split(maxsplit=1)
        token = parts[1].strip() if len(parts) > 1 else ""
        if token:
            link = self.links.get_by_token(token)
            if link and link.tenant:
                tenant = link.tenant
                if link.link_type == "client":
                    self.customers.upsert(tenant_id=tenant.id, max_user_id=max_user_id)
                    self.sessions.upsert(
                        chat_id=chat_id,
                        max_user_id=max_user_id,
                        current_tenant_id=tenant.id,
                        current_step=sm.MENU,
                        context={"tenant_slug": tenant.slug},
                    )
                    self.db.commit()
                    return [self._menu_message(chat_id, tenant.display_name, max_user_id)]
                if link.link_type in {"owner", "admin"}:
                    member = self.members.get_by_tenant_user(tenant.id, max_user_id)
                    if member is None:
                        self.members.create(
                            tenant_id=tenant.id,
                            max_user_id=max_user_id,
                            role="owner",
                        )
                    self.sessions.upsert(
                        chat_id=chat_id,
                        max_user_id=max_user_id,
                        current_tenant_id=tenant.id,
                        current_step=sm.MENU,
                        context={"tenant_slug": tenant.slug, "role": "owner"},
                    )
                    self.db.commit()
                    return [{
                        "chat_id": chat_id, "user_id": max_user_id,
                        "text": (
                            f"Вы привязаны как владелец салона {tenant.display_name}."
                            " Команды: /confirm <booking_id>, /reject <booking_id>"
                        ),
                    }]
            tenant = self.tenants.get_by_slug(token)
            if tenant and tenant.status == "active":
                self.customers.upsert(tenant_id=tenant.id, max_user_id=max_user_id)
                self.sessions.upsert(
                    chat_id=chat_id,
                    max_user_id=max_user_id,
                    current_tenant_id=tenant.id,
                    current_step=sm.MENU,
                    context={"tenant_slug": tenant.slug},
                )
                self.db.commit()
                return [self._menu_message(chat_id, tenant.display_name, max_user_id)]

        # /start without token: return to selected salon menu if known.
        current = self._resolve_tenant(session)
        if current is not None and current.status == "active":
            self.sessions.upsert(
                chat_id=chat_id,
                max_user_id=max_user_id,
                current_tenant_id=current.id,
                current_step=sm.MENU,
                context={"tenant_slug": current.slug},
            )
            self.db.commit()
            return [self._menu_message(chat_id, current.display_name, max_user_id)]

        tenants = self.tenants.list_active()
        if not tenants:
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Сейчас нет доступных салонов."}]
        if len(tenants) == 1:
            tenant = tenants[0]
            self.customers.upsert(tenant_id=tenant.id, max_user_id=max_user_id)
            self.sessions.upsert(
                chat_id=chat_id,
                max_user_id=max_user_id,
                current_tenant_id=tenant.id,
                current_step=sm.MENU,
                context={"tenant_slug": tenant.slug},
            )
            self.db.commit()
            return [self._menu_message(chat_id, tenant.display_name, max_user_id)]

        session.current_step = sm.CHOOSE_TENANT
        session.context = {}
        self.db.add(session)
        self.db.commit()
        lines = ["Выберите салон:"]
        rows = []
        for i, t in enumerate(tenants, start=1):
            lines.append(f"{i}. {t.display_name} (/start {t.slug})")
            rows.append([(f"{i}. {t.display_name}", str(i))])
        return [{"chat_id": chat_id, "user_id": max_user_id, "text": "\n".join(lines), "attachments": [self._kb(rows)]}]

    @staticmethod
    def _kb(rows: list[list[tuple[str, str]]]) -> dict[str, Any]:
        return {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [{"type": "callback", "text": text, "payload": payload} for text, payload in row]
                    for row in rows
                ]
            },
        }

    @staticmethod
    def _date_rows(tenant_tz: str, days: int = 7) -> list[list[tuple[str, str]]]:
        from zoneinfo import ZoneInfo
        from datetime import datetime, timedelta
        tz = ZoneInfo(tenant_tz or "Europe/Moscow")
        now = datetime.now(tz).date()
        weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        rows: list[list[tuple[str, str]]] = []
        for i in range(days):
            d = now + timedelta(days=i)
            label = f"{d.strftime('%d.%m')} ({weekdays[d.weekday()]})"
            if i == 0:
                label = f"Сегодня {label}"
            elif i == 1:
                label = f"Завтра {label}"
            rows.append([(label, d.isoformat())])
        rows.append([("Другая дата", "date:manual")])
        return rows

    @staticmethod
    def _time_rows(tenant_tz: str, preferred_date: str | None = None) -> list[list[tuple[str, str]]]:
        from zoneinfo import ZoneInfo
        from datetime import datetime, timedelta
        tz = ZoneInfo(tenant_tz or "Europe/Moscow")
        now = datetime.now(tz)
        selected = None
        if preferred_date:
            try:
                selected = datetime.strptime(preferred_date, "%Y-%m-%d").date()
            except Exception:
                selected = None
        today = now.date()
        rows: list[list[tuple[str, str]]] = []
        row: list[tuple[str, str]] = []
        for hour in range(10, 21):
            for minute in (0, 30):
                if hour == 20 and minute == 30:
                    continue
                if selected == today:
                    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if candidate <= now:
                        continue
                label = f"{hour:02d}:{minute:02d}"
                row.append((label, label))
                if len(row) == 3:
                    rows.append(row)
                    row = []
        if row:
            rows.append(row)
        if not rows:
            rows = [[("Нет доступного времени сегодня", "date:back")]]
        rows.append([("Другое время", "time:manual"), ("Другая дата", "date:back")])
        return rows

    @staticmethod
    def _slot_rows_from_ctx(ctx: dict, tenant) -> list[list[tuple[str, str]]]:
        slots = ctx.get("slots") or []
        tz = __import__("zoneinfo").ZoneInfo(getattr(tenant, "timezone", "Europe/Moscow") or "Europe/Moscow")
        rows = []
        row = []
        for i, iso in enumerate(slots, start=1):
            try:
                local = __import__("datetime").datetime.fromisoformat(iso).astimezone(tz)
                label = local.strftime("%H:%M")
            except Exception:
                label = iso
            row.append((label, str(i)))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([("Другая дата", "date:back")])
        return rows

    @staticmethod
    def _status_label(status: str | None) -> str:
        return {
            "awaiting_salon": "Ожидает подтверждения салона",
            "pending_confirmation": "Ожидает подтверждения салона",
            "confirmed": "Подтверждена",
            "rejected": "Отклонена",
            "expired": "Истекла",
            "cancelled": "Отменена",
        }.get(str(status or ""), str(status or "-"))

    def _menu_message(self, chat_id: int, tenant_name: str, user_id: int | None = None) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "chat_id": chat_id,
            "text": f"Салон: {tenant_name}\nВыберите действие:",
            "attachments": [self._kb([[("Записаться", "1"), ("Мои заявки", "2")]])],
        }
        if user_id is not None:
            msg["user_id"] = user_id
        return msg

    def _handle_text_step(self, session, chat_id: int, max_user_id: int, text: str):
        step = session.current_step or sm.START
        ctx = dict(session.context or {})
        ctx["max_user_id"] = max_user_id

        if step == sm.CHOOSE_TENANT:
            return self._choose_tenant(session, chat_id, max_user_id, text)

        tenant = self._resolve_tenant(session)
        if tenant is None:
            session.current_step = sm.START
            session.context = {}
            self.db.add(session)
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Сессия устарела. /start"}]

        if step == sm.MENU:
            if text == "1":
                services = self.catalog.list_active_services(tenant.id)
                if not services:
                    self.db.commit()
                    return [{"chat_id": chat_id, "user_id": max_user_id, "text": "В салоне пока нет активных услуг."}]
                ctx = {"tenant_slug": tenant.slug, "services": [str(s.id) for s in services]}
                session.current_step = sm.CHOOSE_SERVICE
                session.context = ctx
                self.db.add(session)
                self.db.commit()
                rows = []
                for i, svc in enumerate(services, start=1):
                    label = f"{svc.name} — {svc.price}₽, {svc.duration_minutes} мин"
                    rows.append([(label[:60], str(i))])
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Выберите услугу:",
                    "attachments": [self._kb(rows)],
                }]
            if text == "2":
                bookings = self.bookings.list_for_user(tenant.id, max_user_id)
                if not bookings:
                    self.db.commit()
                    return [{"chat_id": chat_id, "user_id": max_user_id, "text": "У вас пока нет заявок."}]
                lines = ["Ваши заявки:"]
                for b in bookings[:10]:
                    dt = b.preferred_date or "-"
                    tr = b.preferred_time_range or ""
                    svc_name = ""
                    if b.service_id:
                        svc = self.catalog.get_service(tenant.id, b.service_id)
                        if svc:
                            svc_name = svc.name
                    status = self._status_label(b.status)
                    part = f"- {status}"
                    if svc_name:
                        part += f", {svc_name}"
                    part += f", {dt} {tr}".rstrip()
                    lines.append(part)
                self.db.commit()
                return [{"chat_id": chat_id, "user_id": max_user_id, "text": "\n".join(lines)}]
            self.db.commit()
            return [self._menu_message(chat_id, tenant.display_name, max_user_id)]

        if step == sm.CHOOSE_SERVICE:
            return self._choose_service(session, tenant, chat_id, text, ctx, max_user_id)
        if step == sm.CHOOSE_MASTER:
            return self._choose_master(session, tenant, chat_id, text, ctx, max_user_id)
        if step == sm.CHOOSE_SLOT:
            return self._choose_slot(session, tenant, chat_id, max_user_id, text, ctx)
        if step == sm.ENTER_DATE:
            if text == "date:manual":
                self.db.commit()
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Введите дату в формате YYYY-MM-DD (например 2026-12-01).",
                }]
            normalized = self._normalize_date(text)
            if not normalized:
                self.db.commit()
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Неверная дата. Выберите дату кнопкой или введите YYYY-MM-DD.",
                    "attachments": [self._kb(self._date_rows(getattr(tenant, "timezone", "Europe/Moscow"), 7))],
                }]
            # Disallow past dates in tenant timezone
            from zoneinfo import ZoneInfo
            from datetime import datetime as dt
            tz = ZoneInfo(getattr(tenant, "timezone", "Europe/Moscow") or "Europe/Moscow")
            today = datetime.now(tz).date().isoformat()
            if normalized < today:
                self.db.commit()
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Эта дата уже прошла. Выберите другую дату.",
                    "attachments": [self._kb(self._date_rows(getattr(tenant, "timezone", "Europe/Moscow"), 7))],
                }]
            ctx["preferred_date"] = normalized
            if tenant.booking_mode == "online_booking":
                return self._show_slots(session, tenant, chat_id, ctx, max_user_id)
            session.current_step = sm.ENTER_TIME
            session.context = ctx
            self.db.add(session)
            self.db.commit()
            return [{
                "chat_id": chat_id, "user_id": max_user_id,
                "text": f"Выберите время на {dt.strptime(normalized, '%Y-%m-%d').strftime('%d.%m.%Y')}:",
                "attachments": [self._kb(self._time_rows(getattr(tenant, "timezone", "Europe/Moscow"), normalized))],
            }]
        if step == sm.ENTER_TIME:
            if text == "date:back":
                session.current_step = sm.ENTER_DATE
                session.context = ctx
                self.db.add(session)
                self.db.commit()
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Выберите дату:",
                    "attachments": [self._kb(self._date_rows(getattr(tenant, "timezone", "Europe/Moscow"), 7))],
                }]
            if text == "time:manual":
                self.db.commit()
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Введите удобное время в формате HH:MM или HH:MM-HH:MM (например 12:30 или 12:30-14:00).",
                    "attachments": [self._kb(self._time_rows(getattr(tenant, "timezone", "Europe/Moscow"), ctx.get("preferred_date")))],
                }]
            normalized = self._normalize_time_range(text)
            if not normalized:
                self.db.commit()
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Неверное время. Выберите кнопку или введите HH:MM / HH:MM-HH:MM.",
                    "attachments": [self._kb(self._time_rows(getattr(tenant, "timezone", "Europe/Moscow"), ctx.get("preferred_date")))],
                }]
            # block past time for today
            from zoneinfo import ZoneInfo
            from datetime import datetime as dt
            tz = ZoneInfo(getattr(tenant, "timezone", "Europe/Moscow") or "Europe/Moscow")
            now = datetime.now(tz)
            pref_date = ctx.get("preferred_date")
            if pref_date:
                try:
                    start_hm = normalized.split("-")[0].strip()
                    candidate = dt.strptime(f"{pref_date} {start_hm}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    if candidate <= now:
                        self.db.commit()
                        return [{
                            "chat_id": chat_id, "user_id": max_user_id,
                            "text": "Это время уже прошло. Выберите другое время.",
                            "attachments": [self._kb(self._time_rows(getattr(tenant, "timezone", "Europe/Moscow"), pref_date))],
                        }]
                except Exception:
                    pass
            ctx["preferred_time_range"] = normalized
            session.current_step = sm.ENTER_NAME
            session.context = ctx
            self.db.add(session)
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Как вас зовут?"}]
        if step == sm.ENTER_NAME:
            ctx["customer_name"] = text
            session.current_step = sm.ENTER_PHONE
            session.context = ctx
            self.db.add(session)
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Введите телефон для связи."}]
        if step == sm.ENTER_PHONE:
            phone = self._normalize_phone(text)
            if not phone:
                self.db.commit()
                return [
                    {
                        "chat_id": chat_id, "user_id": max_user_id,
                        "text": "Неверный телефон. Минимум 10 цифр.",
                    }
                ]
            ctx["customer_phone"] = phone
            session.current_step = sm.CONFIRM
            session.context = ctx
            self.db.add(session)
            self.db.commit()
            return [self._confirm_message(chat_id, ctx, max_user_id)]
        if step == sm.CONFIRM:
            if text.lower() in {"1", "да", "yes", "ok", "подтвердить"}:
                return self._create_booking(session, tenant, chat_id, max_user_id, ctx)
            if text.lower() in {"2", "нет", "no", "отмена"}:
                session.current_step = sm.MENU
                session.context = {"tenant_slug": tenant.slug}
                self.db.add(session)
                self.db.commit()
                return [
                    {"chat_id": chat_id, "user_id": max_user_id, "text": "Заявка отменена."},
                    self._menu_message(chat_id, tenant.display_name, max_user_id),
                ]
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Отправьте 1 (да) или 2 (нет)."}]

        session.current_step = sm.MENU
        session.context = {"tenant_slug": tenant.slug}
        self.db.add(session)
        self.db.commit()
        return [self._menu_message(chat_id, tenant.display_name, max_user_id)]

    def _choose_tenant(self, session, chat_id: int, max_user_id: int, text: str):
        tenants = self.tenants.list_active()
        chosen = None
        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(tenants):
                chosen = tenants[idx]
        if chosen is None:
            chosen = self.tenants.get_by_slug(text)
        if chosen is None:
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Отправьте номер или slug салона."}]
        self.customers.upsert(tenant_id=chosen.id, max_user_id=max_user_id)
        self.sessions.upsert(
            chat_id=chat_id,
            max_user_id=max_user_id,
            current_tenant_id=chosen.id,
            current_step=sm.MENU,
            context={"tenant_slug": chosen.slug},
        )
        self.db.commit()
        return [self._menu_message(chat_id, chosen.display_name, max_user_id)]

    def _choose_service(self, session, tenant, chat_id: int, text: str, ctx: dict[str, Any], user_id: int | None = None):
        uid = user_id or ctx.get("max_user_id")
        service_ids = [uuid.UUID(s) for s in ctx.get("services", [])]
        if not text.isdigit():
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": uid, "text": "Отправьте номер услуги."}]
        idx = int(text) - 1
        if idx < 0 or idx >= len(service_ids):
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": uid, "text": "Неверный номер услуги."}]
        service = self.catalog.get_service(tenant.id, service_ids[idx])
        if service is None:
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": uid, "text": "Услуга не найдена. /start"}]
        masters = self.catalog.list_service_masters(tenant.id, service.id)
        ctx["service_id"] = str(service.id)
        ctx["service_name"] = service.name
        ctx["price_snapshot"] = str(service.price)
        ctx["duration_snapshot"] = service.duration_minutes
        ctx["buffer_minutes"] = service.buffer_minutes or 0
        ctx["masters"] = [str(m.id) for m in masters]
        session.current_step = sm.CHOOSE_MASTER
        session.context = ctx
        self.db.add(session)
        self.db.commit()
        rows = []
        active = self.catalog.list_active_masters(tenant.id)
        for i, mid in enumerate(masters, start=1):
            master = next((m for m in active if m.id == mid), None)
            name = master.display_name if master else "Мастер"
            rows.append([(name[:60], str(i))])
        any_idx = str(len(masters) + 1)
        rows.append([("Любой мастер", any_idx)])
        return [{"chat_id": chat_id, "user_id": uid, "text": "Выберите мастера:", "attachments": [self._kb(rows)]}]

    def _choose_master(self, session, tenant, chat_id: int, text: str, ctx: dict[str, Any], user_id: int | None = None):
        uid = user_id or ctx.get("max_user_id")
        masters = [uuid.UUID(m) for m in ctx.get("masters", [])]
        if not text.isdigit():
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": uid, "text": "Отправьте номер мастера."}]
        idx = int(text) - 1
        if idx == len(masters):
            ctx["master_id"] = None
            ctx["master_name"] = "Любой мастер"
        elif 0 <= idx < len(masters):
            active = self.catalog.list_active_masters(tenant.id)
            master = next((m for m in active if m.id == masters[idx]), None)
            ctx["master_id"] = str(masters[idx])
            ctx["master_name"] = master.display_name if master else "Мастер"
        else:
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": uid, "text": "Неверный номер мастера."}]
        session.current_step = sm.ENTER_DATE
        session.context = ctx
        self.db.add(session)
        self.db.commit()
        if tenant.booking_mode == "online_booking" and not ctx.get("master_id"):
            return [{
                "chat_id": chat_id, "user_id": uid,
                "text": "Для online_booking выберите конкретного мастера.",
            }]
        return [{
            "chat_id": chat_id, "user_id": uid,
            "text": "Выберите дату:",
            "attachments": [self._kb(self._date_rows(getattr(tenant, "timezone", "Europe/Moscow"), 7))],
        }]

    def _show_slots(self, session, tenant, chat_id: int, ctx: dict, user_id: int | None = None):
        from datetime import date as date_type

        from app.services.scheduling.slots import get_available_slots

        uid = user_id or ctx.get("max_user_id")
        master_id = uuid.UUID(ctx["master_id"]) if ctx.get("master_id") else None
        if master_id is None:
            self.db.commit()
            return [{
                "chat_id": chat_id, "user_id": uid,
                "text": "Для online_booking выберите конкретного мастера.",
            }]
        service = self.catalog.get_service(tenant.id, uuid.UUID(ctx["service_id"]))
        if service is None:
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": uid, "text": "Услуга не найдена. /start"}]
        try:
            pref_day = date_type.fromisoformat(ctx["preferred_date"])
        except Exception:
            self.db.commit()
            return [{"chat_id": chat_id, "user_id": uid, "text": "Неверная дата."}]
        slots = get_available_slots(
            db=self.db,
            tenant_id=tenant.id,
            master_id=master_id,
            service_duration_minutes=service.duration_minutes,
            buffer_minutes=service.buffer_minutes or 0,
            tenant_tz=tenant.timezone,
            days_ahead=1,
        )
        tz = __import__("zoneinfo").ZoneInfo(tenant.timezone)
        slots = [
            s for s in slots if s.start.astimezone(tz).date() == pref_day
        ][:10]
        if not slots:
            self.db.commit()
            return [{
                "chat_id": chat_id, "user_id": uid,
                "text": "Нет свободных слотов на эту дату. Выберите другую дату:",
                "attachments": [self._kb(self._date_rows(getattr(tenant, "timezone", "Europe/Moscow"), 7))],
            }]
        ctx["slots"] = [s.start.isoformat() for s in slots]
        session.current_step = sm.CHOOSE_SLOT
        session.context = ctx
        self.db.add(session)
        self.db.commit()
        rows = []
        row = []
        for i, sl in enumerate(slots, start=1):
            local = sl.start.astimezone(tz)
            label = local.strftime('%H:%M')
            row.append((label, str(i)))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([("Другая дата", "date:back")])
        return [{
            "chat_id": chat_id, "user_id": uid,
            "text": f"Выберите время на {pref_day.strftime('%d.%m.%Y')}:",
            "attachments": [self._kb(rows)],
        }]
    def _choose_slot(self, session, tenant, chat_id: int, max_user_id: int, text: str, ctx: dict):
        if text == "date:back":
            session.current_step = sm.ENTER_DATE
            session.context = ctx
            self.db.add(session)
            self.db.commit()
            return [{
                "chat_id": chat_id, "user_id": max_user_id,
                "text": "Выберите дату:",
                "attachments": [self._kb(self._date_rows(getattr(tenant, "timezone", "Europe/Moscow"), 7))],
            }]
        slots = ctx.get("slots") or []
        if not text.isdigit():
            self.db.commit()
            return [{
                "chat_id": chat_id, "user_id": max_user_id,
                "text": "Выберите время кнопкой.",
                "attachments": [self._kb(self._slot_rows_from_ctx(ctx, tenant))],
            }]
        idx = int(text) - 1
        if idx < 0 or idx >= len(slots):
            self.db.commit()
            return [{
                "chat_id": chat_id, "user_id": max_user_id,
                "text": "Неверный слот. Выберите кнопку.",
                "attachments": [self._kb(self._slot_rows_from_ctx(ctx, tenant))],
            }]
        ctx["slot_start"] = slots[idx]
        tz = __import__('zoneinfo').ZoneInfo(tenant.timezone)
        local_dt = __import__('datetime').datetime.fromisoformat(slots[idx])
        local = local_dt.astimezone(tz)
        ctx["preferred_time_range"] = local.strftime("%H:%M")
        ctx["slot_start_local"] = local.strftime("%H:%M")
        session.current_step = sm.ENTER_NAME
        session.context = ctx
        self.db.add(session)
        self.db.commit()
        return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Как вас зовут?"}]
    def _confirm_message(self, chat_id: int, ctx: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        text = (
            "Проверьте заявку:\n"
            f"Услуга: {ctx.get('service_name')}\n"
            f"Мастер: {ctx.get('master_name')}\n"
            f"Дата: {ctx.get('preferred_date')}\n"
            f"Время: {ctx.get('preferred_time_range')}\n"
            f"Имя: {ctx.get('customer_name')}\n"
            f"Телефон: {mask_phone(ctx.get('customer_phone'))}"
        )
        msg: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "attachments": [self._kb([[("Подтвердить", "1"), ("Отмена", "2")]])],
        }
        if user_id is not None:
            msg["user_id"] = user_id
        return msg

    def _booking_window(self, tenant, ctx: dict):
        from datetime import datetime as dt, timedelta
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(getattr(tenant, "timezone", "Europe/Moscow") or "Europe/Moscow")
        dur = int(ctx.get("duration_snapshot") or 0)
        buf = int(ctx.get("buffer_minutes") or 0)
        if dur <= 0:
            return None, None
        if ctx.get("slot_start"):
            try:
                start = dt.fromisoformat(ctx["slot_start"])
            except Exception:
                return None, None
            return start, start + timedelta(minutes=dur + buf)

        pref_date = str(ctx.get("preferred_date") or "").strip()
        pref_time = str(ctx.get("preferred_time_range") or ctx.get("slot_start_local") or "").strip()
        if not pref_date or not pref_time:
            return None, None
        start_str = pref_time.split("-")[0].strip()
        try:
            start_naive = dt.strptime(f"{pref_date} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            return None, None
        start = start_naive.replace(tzinfo=tz)
        end_str = pref_time.split("-")[1].strip() if "-" in pref_time else None
        if end_str:
            try:
                end_naive = dt.strptime(f"{pref_date} {end_str}", "%Y-%m-%d %H:%M")
                end = end_naive.replace(tzinfo=tz)
                if end <= start:
                    end = start + timedelta(minutes=dur + buf)
                else:
                    end = end + timedelta(minutes=buf)
                return start, end
            except Exception:
                pass
        return start, start + timedelta(minutes=dur + buf)

    def _create_booking(self, session, tenant, chat_id: int, max_user_id: int, ctx: dict):
        phone = str(ctx.get("customer_phone") or "")
        slot_start = None
        slot_end = None
        booking_mode = tenant.booking_mode
        status = "awaiting_salon"
        expires_at = None
        if booking_mode == "online_booking" and ctx.get("slot_start"):
            from datetime import datetime as dt
            from datetime import timedelta

            slot_start = dt.fromisoformat(ctx["slot_start"])
            dur = int(ctx.get("duration_snapshot") or 0)
            buf = int(ctx.get("buffer_minutes") or 0)
            slot_end = slot_start + timedelta(minutes=dur + buf) if dur else None
            if getattr(tenant, "online_booking_auto_confirm", True):
                status = "confirmed"
            else:
                status = "pending_confirmation"
                hold = int(getattr(tenant, "online_booking_hold_minutes", 15) or 15)
                expires_at = datetime.now(UTC) + timedelta(minutes=max(hold, 1))

        window_start, window_end = self._booking_window(tenant, ctx)
        if ctx.get("master_id") and window_start and window_end:
            master_uuid = uuid.UUID(ctx["master_id"])
            self.bookings.lock_master(tenant.id, master_uuid)
            conflict = self.bookings.has_conflicting_booking(
                tenant_id=tenant.id,
                master_id=master_uuid,
                slot_start=window_start,
                slot_end=window_end,
            )
            if conflict:
                session.current_step = sm.ENTER_DATE
                session.context = ctx
                self.db.add(session)
                self.db.commit()
                return [{
                    "chat_id": chat_id, "user_id": max_user_id,
                    "text": "Это время уже занято у выбранного мастера (учитывается длительность услуги). Выберите другую дату/время.",
                    "attachments": [self._kb(self._date_rows(getattr(tenant, "timezone", "Europe/Moscow"), 7))],
                }]
            if booking_mode == "request_only":
                slot_start, slot_end = window_start, window_end

        booking = Booking(
            tenant_id=tenant.id,
            max_user_id=max_user_id,
            chat_id=chat_id,
            service_id=uuid.UUID(ctx["service_id"]),
            master_id=uuid.UUID(ctx["master_id"]) if ctx.get("master_id") else None,
            slot_start=slot_start,
            slot_end=slot_end,
            preferred_date=ctx.get("preferred_date"),
            preferred_time_range=ctx.get("preferred_time_range") or ctx.get("slot_start_local"),
            status=status,
            booking_mode=booking_mode,
            price_snapshot=ctx.get("price_snapshot"),
            duration_snapshot=ctx.get("duration_snapshot"),
            customer_name_snapshot=ctx.get("customer_name"),
            customer_phone_encrypted=encrypt_value(phone),
            expires_at=expires_at,
        )
        try:
            self.bookings.create(booking)
            self.db.flush()
        except Exception:
            self.db.rollback()
            session.current_step = sm.ENTER_DATE
            session.context = ctx
            self.db.add(session)
            self.db.commit()
            return [{
                "chat_id": chat_id, "user_id": max_user_id,
                "text": "Этот слот уже занят. Выберите другую дату/время.",
            }]
        self.customers.upsert(
            tenant_id=tenant.id,
            max_user_id=max_user_id,
            display_name=ctx.get("customer_name"),
            phone_encrypted=encrypt_value(phone),
        )
        session.current_step = (
            sm.AWAITING_SALON if status in {"awaiting_salon", "pending_confirmation"} else sm.MENU
        )
        session.context = {"tenant_slug": tenant.slug, "last_booking_id": str(booking.id)}
        self.db.add(session)

        owner_msgs = self._notify_owners(tenant.id, booking, ctx)
        self.db.commit()

        if booking.status == "confirmed":
            when = f"{ctx.get('preferred_date')} {ctx.get('preferred_time_range') or ''}".strip()
            client_text = f"Запись подтверждена. Время: {when}"
        elif booking.status == "pending_confirmation":
            when = f"{ctx.get('preferred_date')} {ctx.get('preferred_time_range') or ''}".strip()
            client_text = (
                f"Запись зарезервирована на {when}. "
                "Ожидает подтверждения салона."
            )
        else:
            client_text = "Заявка создана. Статус: ожидает подтверждения салона."
        client_msg = {"chat_id": chat_id, "user_id": max_user_id, "text": client_text}
        return [client_msg, *owner_msgs]

    def _notify_owners(self, tenant_id: uuid.UUID, booking: Booking, ctx: dict):
        owners = self.members.list_active_owners(tenant_id)
        msgs: list[dict[str, Any]] = []
        for owner in owners:
            text = (
                f"Новая заявка\n"
                f"Услуга: {ctx.get('service_name')}\n"
                f"Мастер: {ctx.get('master_name')}\n"
                f"Дата: {ctx.get('preferred_date')}\n"
                f"Время: {ctx.get('preferred_time_range')}\n"
                f"Клиент: {ctx.get('customer_name')} {mask_phone(ctx.get('customer_phone'))}\n"
                f"Подтвердить: /confirm {booking.id}\n"
                f"Отклонить: /reject {booking.id}"
            )
            self.outbox.enqueue(
                tenant_id=tenant_id,
                chat_id=owner.max_user_id,
                payload={"text": text, "user_id": owner.max_user_id},
                dedupe_key=f"booking:{booking.id}:owner_notify:{owner.max_user_id}",
            )
            msgs.append({"chat_id": owner.max_user_id, "user_id": owner.max_user_id, "text": text, "queued": True})
        return msgs

    def _handle_owner_command(self, chat_id: int, max_user_id: int, text: str):
        parts = text.split()
        if len(parts) != 2 or parts[0] not in {"/confirm", "/reject"}:
            return None
        cmd, booking_id_raw = parts
        try:
            booking_id = uuid.UUID(booking_id_raw)
        except ValueError:
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Некорректный ID заявки."}]

        booking = self.bookings.get_by_id(booking_id)
        if booking is None:
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Заявка не найдена."}]

        member = self.members.get_by_tenant_user(booking.tenant_id, max_user_id)
        if member is None or member.role != "owner":
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": "Недостаточно прав."}]

        # Atomic status transition for idempotent owner commands.
        from_statuses = ["awaiting_salon", "pending_confirmation"]
        updated = None
        for fs in from_statuses:
            updated = self.bookings.transition_status(
                tenant_id=booking.tenant_id,
                booking_id=booking.id,
                from_status=fs,
                to_status="confirmed" if cmd == "/confirm" else "rejected",
            )
            if updated is not None:
                break
        if updated is None:
            self.db.refresh(booking)
            return [{"chat_id": chat_id, "user_id": max_user_id, "text": f"Заявка уже обработана: {booking.status}"}]
        booking = updated
        new_status = booking.status

        client_text = (
            "Ваша заявка подтверждена салоном."
            if new_status == "confirmed"
            else "Заявка отклонена салоном. Выберите другое время /start."
        )
        self.outbox.enqueue(
            tenant_id=booking.tenant_id,
            chat_id=booking.chat_id,
            payload={"text": client_text, "user_id": booking.max_user_id},
        )

        owner_text = f"Заявка переведена в статус: {self._status_label(new_status)}."
        return [
            {"chat_id": chat_id, "user_id": max_user_id, "text": owner_text},
            {"chat_id": booking.chat_id, "text": client_text, "queued": True},
        ]

    def _resolve_tenant(self, session):
        if session.current_tenant_id:
            for t in self.tenants.list_active():
                if t.id == session.current_tenant_id:
                    return t
        slug = (session.context or {}).get("tenant_slug")
        if slug:
            return self.tenants.get_by_slug(slug)
        return None

    def _handle_callback(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Contract-agnostic callback adapter.

        MAX callback contract is not fully confirmed; we only route safe text-like
        payloads through the existing text flow. Unknown callbacks are ignored.
        """
        from app.services.webhooks.normalizer import normalize_max_event

        n = normalize_max_event(payload)
        callback_id = n.get("callback_id")
        text = str(n.get("text") or "").strip()
        if not n.get("chat_id") or not n.get("user_id") or not text:
            logger.info(
                "Callback ignored (missing route data): update_type=%s callback_id=%s",
                n.get("event_type"),
                callback_id,
            )
            return []

        # Reuse message flow by presenting normalized text.
        synthetic = {
            "update_type": "message_created",
            "message": {
                "chat_id": n.get("chat_id"),
                "sender": {"user_id": n.get("user_id"), "name": n.get("sender_name")},
                "body": {"text": text},
            },
        }
        logger.info("Callback routed as text: callback_id=%s text=%s", callback_id, text[:80])
        return self._handle_message(synthetic)

    @staticmethod
    def _normalize_date(value: str) -> str | None:
        try:
            d = date.fromisoformat(value.strip())
        except ValueError:
            return None
        if d < datetime.now(UTC).date():
            return None
        return d.isoformat()

    @staticmethod
    def _normalize_time_range(value: str) -> str | None:
        raw = value.strip().replace(" ", "")
        if not raw:
            return None
        if "-" in raw:
            left, right = raw.split("-", 1)
            try:
                t1 = datetime.strptime(left, "%H:%M").time()
                t2 = datetime.strptime(right, "%H:%M").time()
            except ValueError:
                return None
            if t2 <= t1:
                return None
            return f"{t1.strftime('%H:%M')}-{t2.strftime('%H:%M')}"
        try:
            t = datetime.strptime(raw, "%H:%M").time()
        except ValueError:
            return None
        return t.strftime("%H:%M")

    @staticmethod
    def _normalize_phone(value: str) -> str | None:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 10 or len(digits) > 15:
            return None
        return "+" + digits
