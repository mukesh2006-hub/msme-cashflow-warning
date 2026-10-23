def fmt_inr(x) -> str:
    """Indian digit grouping: 1234567 -> '₹12,34,567'."""
    n = int(round(abs(x)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if x < 0 else "") + "₹" + s


def emi(principal: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 12
    return principal * r / (1 - (1 + r) ** -months) if r else principal / months