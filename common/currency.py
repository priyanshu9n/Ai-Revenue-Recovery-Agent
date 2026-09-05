"""
Shared INR currency formatting, used by both app/dashboard.py and
evaluation/run_evaluation.py so the two never drift out of sync again.

Indian numbering convention: values under 1 crore are shown in Lakhs (L),
values of 1 crore or more are shown in Crores (Cr) -- e.g. ₹94.5L but
₹1.23Cr, not ₹123.00L. Amounts throughout this project are stored in paise
(Razorpay's smallest-unit convention), so this always divides by 100 first
to get rupees before scaling to L/Cr.
"""

ONE_LAKH_RUPEES = 100_000
ONE_CRORE_RUPEES = 10_000_000


def format_inr(paise, decimals: int = 2) -> str:
    """
    paise: an amount in paise (int/float). None or invalid input returns "—".

    Examples:
      format_inr(9_500_000_00)   -> "₹95.00L"   (95 lakh rupees)
      format_inr(120_000_000_00) -> "₹1.20Cr"   (1.2 crore rupees)
    """
    try:
        rupees = float(paise) / 100
    except (TypeError, ValueError):
        return "—"

    if abs(rupees) >= ONE_CRORE_RUPEES:
        return f"₹{rupees / ONE_CRORE_RUPEES:.{decimals}f}Cr"
    return f"₹{rupees / ONE_LAKH_RUPEES:.{decimals}f}L"
