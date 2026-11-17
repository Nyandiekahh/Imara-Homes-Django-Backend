"""Generates a Kenyan-market rent receipt PDF for a Payment using reportlab."""
import io

from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def build_receipt_pdf(payment):
	buffer = io.BytesIO()
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A5,
		topMargin=14 * mm,
		bottomMargin=14 * mm,
		leftMargin=14 * mm,
		rightMargin=14 * mm,
	)
	styles = getSampleStyleSheet()
	title_style = ParagraphStyle("ReceiptTitle", parent=styles["Heading1"], fontSize=16, spaceAfter=2)
	small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
	normal = styles["Normal"]

	owner = payment.property.owner
	elements = [
		Paragraph(payment.property.name, title_style),
		Paragraph("Official Rent Payment Receipt", small),
		Spacer(1, 6 * mm),
	]

	if owner.kra_pin:
		elements.append(Paragraph(f"Landlord KRA PIN: {owner.kra_pin}", small))
		elements.append(Spacer(1, 3 * mm))

	info_rows = [
		["Receipt No.", payment.receipt_number or "—"],
		["Tenant", payment.tenancy.user.full_name or payment.tenancy.user.email],
		["Unit", payment.unit.name if payment.unit else "—"],
		["Period", payment.period or "—"],
		["Payment Method", payment.get_payment_method_display()],
		["Date Paid", payment.paid_at.strftime("%d %b %Y, %H:%M") if payment.paid_at else "—"],
	]
	info_table = Table(info_rows, colWidths=[45 * mm, 65 * mm])
	info_table.setStyle(
		TableStyle(
			[
				("FONTSIZE", (0, 0), (-1, -1), 10),
				("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
			]
		)
	)
	elements.append(info_table)
	elements.append(Spacer(1, 6 * mm))

	charge_rows = [["Item", "Amount (KES)"], ["Rent", f"{payment.amount:,.2f}"]]
	for item in payment.charges or []:
		try:
			amount = float(item.get("amount", 0))
		except (TypeError, ValueError):
			amount = 0
		charge_rows.append([item.get("label", "Charge"), f"{amount:,.2f}"])
	if payment.fine:
		charge_rows.append(["Fine", f"{payment.fine:,.2f}"])
	charge_rows.append(["Total", f"{payment.total:,.2f}"])

	charges_table = Table(charge_rows, colWidths=[70 * mm, 40 * mm])
	charges_table.setStyle(
		TableStyle(
			[
				("FONTSIZE", (0, 0), (-1, -1), 10),
				("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
				("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
				("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
				("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
				("ALIGN", (1, 0), (1, -1), "RIGHT"),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("TOPPADDING", (0, 0), (-1, -1), 4),
			]
		)
	)
	elements.append(charges_table)
	elements.append(Spacer(1, 8 * mm))

	if payment.payment_method == "mpesa" and hasattr(payment, "mpesa_transaction"):
		txn = payment.mpesa_transaction
		if txn.mpesa_receipt_number:
			elements.append(Paragraph(f"M-Pesa Receipt: {txn.mpesa_receipt_number}", normal))
			elements.append(Spacer(1, 4 * mm))

	elements.append(Paragraph(f"This receipt was generated automatically by {settings.APP_NAME}.", small))

	doc.build(elements)
	buffer.seek(0)
	return buffer
