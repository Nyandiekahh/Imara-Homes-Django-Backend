import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		abstract = True


def _default_expenditure_rate():
	return Decimal(str(getattr(settings, "DEFAULT_EXPENDITURE_RATE_PERCENT", "40.00")))


def _default_rental_tax_rate():
	return Decimal(str(getattr(settings, "DEFAULT_RENTAL_TAX_RATE_PERCENT", "10.00")))


class Property(TimeStampedModel):
	class PropertyType(models.TextChoices):
		APARTMENT = "apartment", "Apartment Block"
		BUNGALOW_COMPLEX = "bungalow_complex", "Bungalow Complex"
		TOWNHOUSE_COMPLEX = "townhouse_complex", "Townhouse Complex"
		MIXED_USE = "mixed_use", "Mixed Use"
		COMMERCIAL = "commercial", "Commercial Building"
		STANDALONE = "standalone", "Standalone House"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	owner = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="owned_properties",
	)
	name = models.CharField(max_length=255)
	type = models.CharField(max_length=50, choices=PropertyType.choices)
	address = models.CharField(max_length=255, blank=True)
	city = models.CharField(max_length=120, blank=True)
	county = models.CharField(max_length=120, blank=True)
	description = models.TextField(blank=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return self.name


class PropertyAgent(TimeStampedModel):
	"""Caretaker/agent assigned to help manage a property on the owner's behalf."""

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="agents")
	agent = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="agent_assignments",
	)
	assigned_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="agent_assignments_made",
	)
	can_manage_payments = models.BooleanField(default=True)
	can_manage_maintenance = models.BooleanField(default=True)
	can_manage_tenants = models.BooleanField(default=False)
	can_send_communications = models.BooleanField(default=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(fields=["property", "agent"], name="uniq_agent_per_property"),
		]

	def __str__(self):
		return f"{self.agent.email} -> {self.property.name}"


class Unit(TimeStampedModel):
	class UnitType(models.TextChoices):
		BEDSITTER = "bedsitter", "Bedsitter"
		STUDIO = "studio", "Studio"
		BEDROOM_1 = "1_bedroom", "1 Bedroom"
		BEDROOM_2 = "2_bedroom", "2 Bedroom"
		BEDROOM_3 = "3_bedroom", "3 Bedroom"
		BEDROOM_4 = "4_bedroom", "4 Bedroom"
		PENTHOUSE = "penthouse", "Penthouse"
		BUNGALOW = "bungalow", "Bungalow"
		TOWNHOUSE = "townhouse", "Townhouse"
		VILLA = "villa", "Villa"
		SHOP = "shop", "Shop / Commercial"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="units")
	name = models.CharField(max_length=80)
	floor = models.IntegerField(default=1)
	unit_type = models.CharField(max_length=30, choices=UnitType.choices)
	rent_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

	class Meta:
		ordering = ["name"]
		constraints = [
			models.UniqueConstraint(fields=["property", "name"], name="uniq_unit_name_per_property"),
		]

	def __str__(self):
		return f"{self.property.name} - {self.name}"


class PaymentConfig(TimeStampedModel):
	class FineType(models.TextChoices):
		FLAT = "flat", "Flat Fee"
		PERCENTAGE = "percentage", "Percentage"
		PER_DAY = "per_day", "Per Day"
		PERCENTAGE_PER_DAY = "percentage_per_day", "Percentage Per Day"
		NONE = "none", "No Fine"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	property = models.OneToOneField(
		Property,
		on_delete=models.CASCADE,
		related_name="payment_config",
	)
	due_day = models.PositiveSmallIntegerField(default=5)
	fine_type = models.CharField(max_length=30, choices=FineType.choices, default=FineType.NONE)
	fine_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	fine_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
	fine_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	additional_charges = models.JSONField(default=list, blank=True)
	water_bill = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	garbage_bill = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	security_levy = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	custom_charges = models.JSONField(default=list, blank=True)
	# Kenyan rental-income reporting: configurable per property, never hardcoded in views.
	# Defaults come from DEFAULT_EXPENDITURE_RATE_PERCENT / DEFAULT_RENTAL_TAX_RATE_PERCENT env vars.
	expenditure_rate_percent = models.DecimalField(
		max_digits=5, decimal_places=2, default=_default_expenditure_rate,
		help_text="Assumed monthly expenditure as a percentage of collections, used in the revenue report.",
	)
	rental_tax_rate_percent = models.DecimalField(
		max_digits=5, decimal_places=2, default=_default_rental_tax_rate,
		help_text="Rental income tax rate applied to monthly revenue (collections minus expenditure).",
	)

	def __str__(self):
		return f"Payment config - {self.property.name}"


class PropertyDocument(TimeStampedModel):
	class DocumentType(models.TextChoices):
		LEASE_AGREEMENT = "lease_agreement", "Lease Agreement"
		TENANCY = "tenancy", "Tenancy"
		OTHER = "other", "Other"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	property = models.ForeignKey(
		Property,
		on_delete=models.CASCADE,
		related_name="documents",
	)
	document_type = models.CharField(max_length=40, choices=DocumentType.choices, default=DocumentType.OTHER)
	file = models.FileField(upload_to="property_documents/%Y/%m/")
	uploaded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="uploaded_property_documents",
	)

	def __str__(self):
		return f"{self.property.name} - {self.document_type}"
