from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DialogState:
    step: str
    context: dict[str, Any]


START = "start"
CHOOSE_TENANT = "choose_tenant"
MENU = "menu"
CHOOSE_SERVICE = "choose_service"
CHOOSE_MASTER = "choose_master"
ENTER_DATE = "enter_date"
ENTER_TIME = "enter_time"
ENTER_NAME = "enter_name"
ENTER_PHONE = "enter_phone"
CONFIRM = "confirm"
AWAITING_SALON = "awaiting_salon"


def initial_state() -> DialogState:
    return DialogState(step=START, context={})


def reset_booking_context(context: dict[str, Any]) -> dict[str, Any]:
    keep = {k: context.get(k) for k in ["tenant_slug"] if context.get(k) is not None}
    return keep
