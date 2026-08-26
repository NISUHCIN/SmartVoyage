from utils.redact import redact_sensitive


def test_redact_masks_phone():
    assert "138****1234" in redact_sensitive("联系电话 13812341234")


def test_redact_masks_email():
    assert "ab***@example.com" in redact_sensitive("邮箱 ab@example.com")


def test_redact_masks_id_card():
    assert "110101********1234" in redact_sensitive("身份证 110101199001011234")


def test_redact_keeps_plain_text():
    assert redact_sensitive("北京到上海高铁") == "北京到上海高铁"
