"""Builds the itemized non-rent charges (water, garbage, security, custom)
for a tenancy's payment, read from the property's PaymentConfig. Nothing here
is hardcoded — every label and amount comes from what the owner configured."""
from decimal import Decimal


def build_charges_breakdown(tenancy):
	if not tenancy or not tenancy.property_id:
		return []

	config = getattr(tenancy.property, "payment_config", None)
	if not config:
		return []

	charges = []
	if config.water_bill:
		charges.append({"code": "water", "label": "Water", "amount": str(config.water_bill)})
	if config.garbage_bill:
		charges.append({"code": "garbage", "label": "Garbage Collection", "amount": str(config.garbage_bill)})
	if config.security_levy:
		charges.append({"code": "security", "label": "Security Levy", "amount": str(config.security_levy)})

	for item in config.custom_charges or []:
		if not isinstance(item, dict):
			continue
		label = item.get("label") or item.get("name") or item.get("value")
		amount = item.get("amount", 0)
		if label and amount:
			charges.append({"code": item.get("value", label.lower()), "label": label, "amount": str(amount)})

	return charges


def charges_total(charges):
	total = Decimal("0")
	for item in charges or []:
		try:
			total += Decimal(str(item.get("amount", 0)))
		except Exception:
			continue
	return total
