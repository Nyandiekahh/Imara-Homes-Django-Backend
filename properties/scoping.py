"""Shared helpers for scoping querysets to what a user (owner, agent, or tenant)
is allowed to see. Centralised here so every app (tenancies, leases, payments,
maintenance, communications) applies the same rule for caretaker/agent access
instead of re-implementing owner-only checks.
"""

from .models import Property, PropertyAgent


def accessible_property_ids(user, permission=None):
	"""Return a queryset of Property ids the given user can act on.

	permission: optional PropertyAgent boolean field name (e.g. "can_manage_payments")
	to further restrict which assigned properties an agent may act on for a
	specific feature area. Owners and admins always have full access to their
	own properties.
	"""
	role = getattr(user, "role", None)

	if role == "admin" or getattr(user, "is_superuser", False):
		return Property.objects.all().values_list("id", flat=True)

	if role == "owner":
		return Property.objects.filter(owner=user).values_list("id", flat=True)

	if role == "agent":
		qs = PropertyAgent.objects.filter(agent=user, is_active=True)
		if permission:
			qs = qs.filter(**{permission: True})
		return qs.values_list("property_id", flat=True)

	return Property.objects.none().values_list("id", flat=True)


def accessible_properties(user, permission=None):
	return Property.objects.filter(id__in=accessible_property_ids(user, permission=permission))


def is_manager(user):
	"""True if the user manages properties in some capacity (owner/agent/admin)."""
	return getattr(user, "role", None) in {"owner", "agent", "admin"} or getattr(user, "is_superuser", False)
