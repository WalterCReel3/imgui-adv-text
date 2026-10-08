def total(prices, tax_rate=0.21):
    subtotal = sum(prices)
    if subtotal >= 100:
        discount = subtotal * 0.05
    else:
        discount = 0.0
    taxed = (subtotal - discount) * (1 + tax_rate)
    return round(taxed, 2)


def label(item, width=24):
    name = item["name"].strip()
    return name.ljust(width) + format(item["price"], ">8.2f")


def receipt(items):
    lines = [label(item) for item in items]
    lines.append("-"  *  32)
    lines.append("total".ljust(24) + format(total([item["price"] for item in items]), ">8.2f"))
    return "\n".join(lines)
