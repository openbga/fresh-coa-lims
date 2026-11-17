"""The sidebar: its sections, items, who sees them and which item a page marks current.

This is the one declaration of the route-to-item mapping (docs/ui-standards.md, "One destination
has one navigation home"). An item marks the page current when the page's URL namespace is one of
its namespaces, or its view name is one of its views. A route belongs to one item at most; account
pages other than the listed ones mark none. Visibility follows the flags of
accounts.context_processors.account_navigation; views still enforce every permission.
"""

from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str
    icon: str
    namespaces: tuple[str, ...] = ()  # every page of these URL namespaces marks the item
    views: tuple[str, ...] = ()  # further view names ("core:rules") that mark it
    except_views: tuple[str, ...] = ()  # pages of its namespaces that belong to another item
    requires: str = ""  # context flag that must be true to show the item


@dataclass(frozen=True)
class NavSection:
    key: str
    label: str
    items: tuple[NavItem, ...]
    requires: str = ""  # context flag that must be true to show the section


SECTIONS = (
    NavSection(
        "work",
        "Work",
        (
            NavItem("Dashboard", "quality:dashboard", "house", views=("quality:dashboard",)),
            NavItem(
                "Lots",
                "quality:lot_list",
                "box-seam",
                ("quality",),
                except_views=("quality:dashboard",),
            ),
            NavItem("Sampling", "sampling:lots", "eyedropper", ("sampling",)),
            NavItem("Testing", "analytical:test_list", "clipboard2-data", ("analytical",)),
            NavItem("Stability", "stability:overview", "thermometer-half", ("stability",)),
            NavItem("Laboratory", "laboratory:overview", "tools", ("laboratory",)),
        ),
        requires="can_view_workspace",
    ),
    NavSection(
        "configuration",
        "Configuration",
        (
            NavItem("Specifications", "catalog:specifications", "file-earmark-ruled", ("catalog",)),
            NavItem("Suppliers", "suppliers:list", "truck", ("suppliers",)),
            NavItem(
                "Rule sets", "core:rules", "list-check", views=("core:rules", "core:rule_approve")
            ),
        ),
        requires="can_view_workspace",
    ),
    NavSection(
        "records",
        "Records",
        (
            NavItem("Certificates", "reporting:list", "file-earmark-check", ("reporting",)),
            NavItem("Validation", "validation:use_list", "ui-checks", ("validation",)),
            NavItem(
                "Audit trail",
                "core:audit",
                "clock-history",
                views=("core:audit",),
                requires="can_view_audit",
            ),
        ),
        requires="can_view_workspace",
    ),
    NavSection(
        "account",
        "Account",
        (
            NavItem("Signature PIN", "core:pin", "key", views=("core:pin",)),
            NavItem(
                "Account access",
                "accounts:access",
                "person-circle",
                views=(
                    "accounts:access",
                    "accounts:password_change",
                    "accounts:two_factor",
                    "accounts:two_factor_setup",
                    "accounts:security_key_add",
                    "accounts:single_sign_on",
                ),
            ),
            NavItem(
                "Users and roles",
                "accounts:user_list",
                "people",
                views=(
                    "accounts:user_list",
                    "accounts:user_create",
                    "accounts:user_detail",
                    "accounts:user_action",
                ),
                requires="can_manage_accounts",
            ),
            NavItem(
                "Sign-in announcement",
                "accounts:announcement",
                "megaphone",
                views=("accounts:announcement",),
                requires="can_manage_accounts",
            ),
        ),
        requires="is_authenticated",
    ),
)


def _flag(flags, name):
    return not name or bool(flags.get(name))


def nav_sections(request, flags):
    """The visible sections, each {key, label, items: [{label, url, icon, current}]}.

    flags: the account_navigation values plus is_authenticated. Empty sections are left out.
    """
    match = getattr(request, "resolver_match", None)
    namespace = match.namespace if match else ""
    view_name = match.view_name if match else ""
    sections = []
    for section in SECTIONS:
        if not _flag(flags, section.requires):
            continue
        items = [
            {
                "label": item.label,
                "url": reverse(item.url_name),
                "icon": item.icon,
                "current": view_name not in item.except_views
                and (namespace in item.namespaces or view_name in item.views),
            }
            for item in section.items
            if _flag(flags, item.requires)
        ]
        if items:
            sections.append({"key": section.key, "label": section.label, "items": items})
    return sections
