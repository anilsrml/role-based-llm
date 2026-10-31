from pathlib import Path

import casbin

_here = Path(__file__).parent
_enforcer = casbin.Enforcer(str(_here / "rbac_model.conf"), str(_here / "rbac_policy.csv"))


def allowed_tools(role: str) -> set[str]:
    # Implicit permissions include the ones inherited down the hierarchy (patron > sekreter > isci).
    return {obj for _, obj in _enforcer.get_implicit_permissions_for_user(role)}


def can_use(role: str, tool: str) -> bool:
    return _enforcer.enforce(role, tool)
