"""日志脱敏：手机号、邮箱、身份证号不落明文。"""
import re

_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")


def redact_sensitive(text: str) -> str:
    if not text:
        return text
    text = _ID_CARD_RE.sub(lambda m: m.group(0)[:6] + "********" + m.group(0)[-4:], text)
    text = _PHONE_RE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], text)
    text = _EMAIL_RE.sub(lambda m: m.group(0)[:2] + "***@" + m.group(0).split("@")[-1], text)
    return text
