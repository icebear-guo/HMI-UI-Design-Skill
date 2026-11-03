DEFAULT_BRAND="工控北极熊（抖音）"
def resolve_brand(company_name=None):
    if company_name is None or not str(company_name).strip():return DEFAULT_BRAND
    return str(company_name).strip()
